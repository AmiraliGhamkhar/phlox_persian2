"""Context-biasing vocabulary for ASR (plan ref A2).

Whisper-family models accept an ``initial prompt``; supplying domain terms
that are likely to occur materially improves recognition of rare words,
names and clinical vocabulary (measured: R-WER 23.7%→18.0%, OOV-WER 60%→37.1%
for zero-shot prompt biasing — B-Whisper, arXiv 2502.11572).

Phlox can build this list from data it already stores: the patient being
documented, their problem list, the clinic's recurring conditions and the
clinician's identity/specialty. Only *terms*, never sentences, and never
free-text clinical conclusions — the prompt is an acoustic prior, not a
licence for the model to expect particular statements.

The same list feeds Speechmatics ``custom_vocabulary`` (batch) and
``additional_vocab`` (realtime), which are first-class vendor biasing APIs.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TERMS = 60  # whisper prompt window is 224 tokens; terms are short
_MAX_PROMPT_CHARS = 900
_TERM_MAX_LEN = 60
_TERM_MIN_LEN = 2

# Drop terms that would smuggle instructions or noise into the prompt.
_REJECTED = re.compile(r"[<>{}\[\]`$\\|]|https?://|[\n\r\t]", re.IGNORECASE)
_ALLOWED = re.compile(r"^[\w؀-ۿ\u060c\u060d .,'’\-+/()&۰-۹0-9]+$", re.UNICODE)


def _clean_term(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    term = re.sub(r"\s+", " ", raw).strip(" .,;:،؛")
    if not (_TERM_MIN_LEN <= len(term) <= _TERM_MAX_LEN):
        return None
    if _REJECTED.search(term) or not _ALLOWED.match(term):
        return None
    # Pure digits/acronyms-only noise and single letters add no biasing value.
    if re.fullmatch(r"[0-9۰-۹\W]+", term):
        return None
    return term


def _dedupe(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out


def build_bias_terms(
    patient_context: dict[str, Any] | None = None,
    primary_condition: str | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Build a conservative, high-precision bias term list.

    Sources (in priority order): patient display name parts, the encounter's
    primary condition, this patient's known conditions from history, the
    clinician name/specialty, then the clinic's most frequent conditions.
    """
    terms: list[str] = []

    context = patient_context or {}
    name = context.get("name")
    if isinstance(name, str):
        parts = [p for p in re.split(r"\s+", name.strip()) if p]
        # Bias on the surname (and full name) rather than short given names,
        # which create false positives.
        if len(parts) > 1:
            terms.append(" ".join(parts))
            terms.append(parts[-1])

    if primary_condition:
        terms.append(str(primary_condition))

    if config:
        for key in ("CLINICIAN_NAME", "CLINICIAN_SPECIALTY"):
            value = config.get(key)
            if value:
                terms.append(str(value))

    cleaned: list[str] = []
    for term in terms:
        value = _clean_term(term)
        if value:
            cleaned.append(value)

    # Clinic-wide recurring conditions (cheap DB read; never fatal).
    try:
        from server.database.repositories.patient_search import (
            get_unique_primary_conditions,
        )

        for condition in get_unique_primary_conditions() or []:
            value = _clean_term(condition)
            if value:
                cleaned.append(value)
    except Exception:  # noqa: BLE001 — biasing is best-effort, never fatal
        logger.debug("ASR bias lexicon skipped", exc_info=True)

    return _dedupe(cleaned)[:_MAX_TERMS]


def load_patient_bias_terms(note_id: int | None) -> list[str]:
    """Active problem list for the current patient (exact-match history)."""
    if not note_id:
        return []
    try:
        from server.database.repositories.encounter import get_patient_by_id

        patient = get_patient_by_id(note_id)
        if not patient:
            return []
        terms: list[str] = []
        conditions = patient.get("conditions") or []
        if isinstance(conditions, str):
            import json

            try:
                conditions = json.loads(conditions)
            except ValueError:
                conditions = []
        for condition in conditions:
            if isinstance(condition, dict) and condition.get("name"):
                terms.append(str(condition["name"]))
            elif isinstance(condition, str):
                terms.append(condition)
        return [t for t in (_clean_term(x) for x in terms) if t]
    except Exception:  # noqa: BLE001
        logger.debug("patient bias terms skipped", exc_info=True)
        return []


def build_initial_prompt(terms: list[str]) -> str | None:
    """Join bias terms into a whisper-compatible prompt, capped to the
    224-token prompt window (≈900 chars for short terms)."""
    if not terms:
        return None
    prompt = "، ".join(terms)
    return prompt[:_MAX_PROMPT_CHARS].strip() or None


def build_custom_vocabulary(terms: list[str]) -> list[str] | None:
    """Speechmatics-compatible custom vocabulary (batch: plain strings)."""
    if not terms:
        return None
    capped = [t for t in terms if len(t) <= 50][:300]
    return capped or None


def build_additional_vocab(terms: list[str]) -> list[dict[str, Any]] | None:
    """Speechmatics realtime additional_vocab entries.

    Multi-word values are split into single words for biasing; restricted
    items (identifiers/names) get ``restricted: True`` so they can only
    appear as the exact bias word. We deliberately do not mark restricted —
    clinical terms must remain freely usable; over-restriction hurts WER.
    """
    if not terms:
        return None
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in terms:
        for word in re.split(r"\s+", term):
            word = word.strip(" .,()")
            if len(word) < 3 or word.casefold() in seen:
                continue
            seen.add(word.casefold())
            entries.append({"content": word})
    return entries[:100] or None
