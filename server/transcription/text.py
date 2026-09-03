import asyncio
import hashlib
import logging
import os
import time
from typing import Any

from rapidfuzz import fuzz

from server.database.config.manager import config_manager
from server.llm_client import repair_json
from server.llm_client.client import get_llm_client
from server.schemas.grammars import MultiFieldResponse
from server.schemas.templates import TemplateField, TemplateResponse
from server.transcription.entailment import maybe_check_claims
from server.transcription.hygiene import deterministic_options
from server.transcription.refinement import refine_field_content
from server.transcription.verification import (
    VerificationReport,
    join_bullets,
    split_bullets,
    verify_draft,
    verify_final_fields,
    verify_mode,
)

logger = logging.getLogger(__name__)


async def process_transcription(
    transcript_text: str,
    template_fields: list[TemplateField],
    patient_context: dict[str, str | None],
    is_ambient: bool = True,
    primary_condition: str | None = None,
) -> dict[str, Any]:
    """
    Process the transcribed text to generate summaries for non-persistent template fields.
    """
    process_start = time.perf_counter()

    try:
        # Filter for non-persistent fields only
        non_persistent_fields = [field for field in template_fields if not field.persistent]

        total_fields = len(non_persistent_fields)

        # Process only non-persistent fields concurrently with mode-specific summarization
        mode_label = "Ambient" if is_ambient else "Dictate"
        logger.info(f"Processing {total_fields} fields ({mode_label} Mode)...")
        raw_results_dict = await process_all_fields_concurrently(
            transcript_text, non_persistent_fields, patient_context, is_ambient, primary_condition
        )

        # Quote-first verification of the DRAFT against the transcript, run
        # before refinement so paraphrasing cannot mask fabrication
        # (plan ref B1). Default policy flags; strict mode drops the
        # unsupported draft bullets instead.
        draft_contents = dict(raw_results_dict)
        verification_report = None
        if transcript_text and transcript_text.strip():
            per_field_points = {k: split_bullets(v) for k, v in raw_results_dict.items()}
            kept_points, verification_report = verify_draft(per_field_points, transcript_text)
            for key, points in kept_points.items():
                if points != per_field_points[key]:
                    raw_results_dict[key] = join_bullets(points)
            if verification_report.flagged:
                logger.warning(
                    "Transcript verification flagged %d unsupported draft bullet(s) (mode=%s)",
                    len(verification_report.unsupported),
                    verification_report.mode,
                )

        # Convert to list of TemplateResponse for compatibility with refinement step
        raw_results = [
            TemplateResponse(field_key=k, content=v) for k, v in raw_results_dict.items()
        ]
        logger.info(f"Successfully summarised {total_fields} fields")

        # Refine all results concurrently
        logger.info(f"Refining {total_fields} fields...")
        refinement_reverts: list[dict] = []
        refined_results = await asyncio.gather(
            *[
                refine_field_content(
                    result.content,
                    field,
                    is_ambient=is_ambient,
                    drift_sink=refinement_reverts,
                )
                for result, field in zip(raw_results, non_persistent_fields, strict=True)
            ]
        )
        logger.info(f"Successfully refined {total_fields} fields")

        # Combine results into a dictionary
        processed_fields = {
            field.field_key: refined_content
            for field, refined_content in zip(non_persistent_fields, refined_results, strict=True)
        }

        # Numeric / negation trace over the FINAL text (plan ref A6): digits
        # and polarity must survive extraction AND refinement unchanged; any
        # drift is surfaced for clinician review, never silently rewritten.
        if transcript_text and transcript_text.strip():
            verification_report = verify_final_fields(
                processed_fields,
                transcript_text,
                verification_report or VerificationReport(mode=verify_mode()),
            )
            if refinement_reverts:
                verification_report.refinement_reverts = refinement_reverts

            # B2: independent entailment pass (separate call, claims judged
            # against the transcript alone). Gated + fail-open: it can only
            # add review findings, never block or rewrite the note.
            entailment = await maybe_check_claims(processed_fields, transcript_text)
            if entailment:
                verification_report.entailment = entailment

            if verification_report.flagged:
                logger.warning(
                    "Transcript verification: %d numeric and %d negation issue(s), "
                    "%d entailment flag(s) in final fields",
                    len(verification_report.number_problems),
                    len(verification_report.negation_problems),
                    int((entailment or {}).get("counts", {}).get("flagged") or 0),
                )

        process_duration = time.perf_counter() - process_start

        return {
            "fields": processed_fields,
            "draft_fields": draft_contents,
            "verification": verification_report.to_dict() if verification_report else {},
            "process_duration": float(f"{process_duration:.2f}"),
        }

    except Exception as e:
        logger.error(f"Error in process_transcription: {e}")
        raise


def _vote_k() -> int:
    """Self-consistency sample count (plan ref B9); 1 = disabled (default).

    With the deterministic defaults (temperature 0, seed 0) repeated draws are
    identical, so voting only makes sense on sampling endpoints — that is
    exactly why it stays opt-in via PHLOX_ASR_VOTE_K (2..5).
    """
    try:
        return max(1, min(5, int(os.environ.get("PHLOX_ASR_VOTE_K", "1"))))
    except (TypeError, ValueError):
        return 1


def _consensus(results: list[dict[str, str]]) -> dict[str, str]:
    """Pick the medoid draft per field: the variant most consistent with the
    others wins; agreement across independent draws is the support signal."""

    keys = list(results[0].keys())
    consensus: dict[str, str] = {}
    for key in keys:
        variants = [result.get(key, "") for result in results]
        if len(set(variants)) <= 1:
            consensus[key] = variants[0]
            continue
        scores = [sum(fuzz.token_set_ratio(a, b) for b in variants) for a in variants]
        consensus[key] = variants[max(range(len(scores)), key=scores.__getitem__)]
    return consensus


async def process_all_fields_concurrently(
    transcript_text: str,
    fields: list[TemplateField],
    patient_context: dict[str, str | None],
    is_ambient: bool = True,
    primary_condition: str | None = None,
    intro_override: str | None = None,
) -> dict[str, str]:
    """Process all template fields in one (or, when voting is enabled, k) LLM
    call(s) and return the consensus draft."""
    vote_k = _vote_k()
    if vote_k <= 1:
        return await _extraction_single(
            transcript_text,
            fields,
            patient_context,
            is_ambient,
            primary_condition,
            intro_override,
        )
    results = await asyncio.gather(
        *[
            _extraction_single(
                transcript_text,
                fields,
                patient_context,
                is_ambient,
                primary_condition,
                intro_override,
                sampling_seed=seed,
            )
            for seed in range(vote_k)
        ]
    )
    results = [result for result in results if result]
    if not results:
        return {}
    return _consensus(results)


async def _extraction_single(
    transcript_text: str,
    fields: list[TemplateField],
    patient_context: dict[str, str | None],
    is_ambient: bool = True,
    primary_condition: str | None = None,
    intro_override: str | None = None,
    sampling_seed: int | None = None,
) -> dict[str, str]:
    """
    Process all template fields in a single LLM call using structured output.

    Builds a unified prompt with all field system prompts and patient context,
    then parses the multi-field response into a dictionary of formatted contents.
    """

    max_retries = 1

    for attempt in range(max_retries + 1):
        try:
            config = config_manager.get_config()
            options = deterministic_options(
                config_manager.get_prompts_and_options()["options"]["general"]
            )
            if sampling_seed is not None:
                # Self-consistency voting needs variance; distinct seeds with
                # a mild temperature produce genuinely independent hypotheses
                # whose agreement we then measure (plan ref B9).
                options = {**options, "temperature": 0.7, "seed": sampling_seed}

            client = get_llm_client()
            response_format = MultiFieldResponse.model_json_schema()
            model_name = config["PRIMARY_MODEL"]

            # Build the combined system prompt with all field instructions
            field_instructions = []
            for field in fields:
                field_instruction = f"""FIELD: {field.field_key}
NAME: {field.field_name}
INSTRUCTIONS: {(field.system_prompt or "").strip()}"""
                field_instructions.append(field_instruction)

            patient_context_str = _build_patient_context(patient_context)

            # Use mode-specific intro for the system prompt
            if intro_override is not None:
                intro = intro_override
            elif is_ambient:
                intro = "Extract relevant information for each of the following fields from the medical transcript."
            else:
                intro = "Extract and organize information from the clinician's direct dictation for each of the following fields."

            if primary_condition:
                intro += (
                    f" This is a returning patient who sees the clinician for {primary_condition}."
                )

            system_content = f"""{intro}

{patient_context_str}

For each field, extract only the most relevant discussion points. If no relevant information is found for a field, return an empty list for that field.

EVIDENCE RULES (mandatory, documentation-safety):
- Each key point must be a short VERBATIM excerpt of what was actually said in the transcript — do not paraphrase, complete, or infer.
- Never add a fact that is not spoken in the transcript (no prior knowledge, no "typical" doses, no invented follow-ups). If something was not said, leave it out.
- Keep numbers, doses, frequencies, dates, medication names and identifiers exactly as spoken; never expand or normalise abbreviations.
- Preserve negations and uncertainty exactly ("no chest pain" must never become "chest pain"; "maybe" must stay hedged).
- If a field has no supported content, return an empty list — an empty list is always preferred over a plausible guess.

FIELDS:
{chr(10).join(field_instructions)}

Output MUST be ONLY valid JSON with top-level key "field_summaries" (object mapping field_key to array of strings)."""

            # The transcript is DATA, never instructions: imperative
            # sentences inside it are part of the conversation and must not
            # alter this task (prompt-injection fencing, plan ref B8).
            request_body = [
                {"role": "system", "content": system_content},
                {
                    "role": "user",
                    "content": (
                        "<clinical_transcript_data>\n"
                        f"{transcript_text}\n"
                        "</clinical_transcript_data>"
                    ),
                },
            ]

            # Deterministic by default (plan ref B4): no random seed — the
            # provider options temperature controls sampling; prompt hash is
            # logged so every generation is reproducible from logs.
            prompt_hash = hashlib.sha256(
                (system_content + "\n" + transcript_text).encode("utf-8")
            ).hexdigest()[:12]

            logger.info(
                f"Processing {len(fields)} fields in one call "
                f"(attempt {attempt + 1}/{max_retries + 1}, prompt={prompt_hash})..."
            )

            response = await client.chat(
                model=model_name,
                messages=request_body,
                format=response_format,
                options=options,
            )

            # Extract and repair JSON
            content = response["message"]["content"]
            repaired_content = repair_json(content)

            # Validate against schema
            multi_field_response = MultiFieldResponse.model_validate_json(repaired_content)

            # Convert to dict of formatted strings (with bullet points)
            formatted_results = {}
            for field in fields:
                key_points = multi_field_response.field_summaries.get(field.field_key, [])
                formatted_content = "\n".join(
                    f"• {_capitalize_first_char(point.strip())}" for point in key_points
                )
                formatted_results[field.field_key] = formatted_content

            logger.info(f"Successfully processed {len(fields)}")

            return formatted_results

        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Error processing all fields concurrently (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying..."
                )
                continue
            else:
                logger.error(
                    f"Error processing all fields concurrently after {max_retries + 1} attempts: {e}"
                )
                raise
    raise RuntimeError("Unreachable: process_all_fields_concurrently exhausted retries")


def _capitalize_first_char(text: str) -> str:
    """Capitalize the first character of a string."""
    if not text:
        return text
    return text[0].upper() + text[1:] if text else text


def _build_patient_context(context: dict[str, str | None]) -> str:
    """
    Build patient context string from dictionary.

    Args:
        context (Dict[str, str]): Patient context (name, dob, gender, etc.).

    Returns:
        str: A formatted patient context string.
    """
    context_parts = []
    if context.get("name"):
        context_parts.append(f"Patient name: {context['name']}")
    if context.get("age"):
        context_parts.append(f"Age: {context['age']}")
    if context.get("gender"):
        context_parts.append(f"Gender: {context['gender']}")
    if context.get("dob"):
        context_parts.append(f"DOB: {context['dob']}")

    return " ".join(context_parts)
