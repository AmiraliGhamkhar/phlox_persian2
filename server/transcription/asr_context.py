"""Context-biasing vocabulary for ASR (plan ref A2, W2.5).

Whisper-family models accept an ``initial prompt``; supplying domain terms
that are likely to occur materially improves recognition of rare words,
names and clinical vocabulary (measured: R-WER 23.7%→18.0%, OOV-WER 60%→37.1%
for zero-shot prompt biasing — B-Whisper, arXiv:2502.11572).

Cap trade-off: the list is hard-capped at 60 terms / ~900 chars. Whisper's
initial-prompt window is 224 tokens, and prompt biasing shows strongly
diminishing returns past a few dozen terms while crowding out the
spoken-form context line; independent CTC-based biasing work on OWSM-style
multilingual ASR (arXiv:2506.09448) reports the same small-list sweet spot.
Longer lists risk hurting more than helping, so we keep this conservative.

When the list is large enough to matter (≥10 terms), the prompt is prefixed
with a short spoken-style Persian context line (CB-Whisper "spoken form
hint" pattern) so the acoustic prior reads like visit speech, not a
keyword dump.

The simplified app keeps no patient record, so the list is built from the
clinician's identity/specialty plus the bundled Persian-English medical
dictionary. Only *terms*, never sentences, and never free-text clinical
conclusions — the prompt is an acoustic prior, not a licence for the model
to expect particular statements.

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

# W2.5: spoken-form hint prefix (plan example), used when ≥ this many terms.
_SPOKEN_PREFIX = "پیاده‌سازی ویزیت پزشکی شامل مواردی مانند "
_SPOKEN_PREFIX_MIN_TERMS = 10

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

    Sources (in priority order): the optional display-name/condition hints
    passed by the caller, the clinician name/specialty, then the bundled
    medical dictionary. The app keeps no patient record, so callers pass
    ``None`` and the dictionary layer does the heavy lifting.
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

    # Base medical-terminology layer from the bundled Persian-English
    # dictionary: patient-specific terms above keep priority, and common
    # clinical vocabulary (symptoms, conditions, meds, labs, oncology) fills
    # whatever capacity remains. Best-effort — never fatal.
    try:
        from server.data.medical_dictionary import asr_bias_terms

        for term in asr_bias_terms():
            value = _clean_term(term)
            if value:
                cleaned.append(value)
    except Exception:  # noqa: BLE001 — biasing is best-effort, never fatal
        logger.debug("ASR dictionary bias layer skipped", exc_info=True)

    return _dedupe(cleaned)[:_MAX_TERMS]


def build_initial_prompt(terms: list[str]) -> str | None:
    """Join bias terms into a whisper-compatible prompt, capped to the
    224-token prompt window (≈900 chars).

    With ≥ ``_SPOKEN_PREFIX_MIN_TERMS`` terms the list is preceded by a
    short spoken-style Persian context line (CB-Whisper "spoken form hint"
    pattern, arXiv:2502.11572); short lists stay a pure term list. The
    prefix counts against the same 900-char cap.
    """
    if not terms:
        return None
    prompt = "، ".join(terms)
    if len(terms) >= _SPOKEN_PREFIX_MIN_TERMS:
        prompt = _SPOKEN_PREFIX + prompt
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
