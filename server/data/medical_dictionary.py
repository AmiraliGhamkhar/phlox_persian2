"""Bilingual Persian-English medical terminology dictionary.

Loads the curated term lists in ``server/data/terms/*.json`` and serves the
three clinical surfaces that consume it:

* **Chat lookup** — ``search()`` fuzzy-matches a clinician's query (Persian or
  English) against both sides and returns the best Persian/English pairs so
  the assistant can answer "what does this term mean?".
* **Refinement terminology reference** — ``terminology_reference_block()``
  finds the dictionary terms that actually occur in a draft and renders a
  compact Persian⇄English table appended to the refinement system prompt, so
  the polish pass can normalise transliterated / spelled-out English medical
  terms to the standard form.
* **ASR biasing** — ``asr_bias_terms()`` yields high-value Persian terms to
  feed the Whisper initial prompt / Speechmatics vocabularies.

The data is static and version-controlled; the loader caches it in-process so
repeated calls (per field, per encounter) are cheap. All public functions are
defensive: a missing or corrupt data file degrades to "no terms" rather than
raising into a clinical pipeline.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TERMS_DIR = Path(__file__).parent / "terms"

# Categories weighted for ASR biasing: the app is hematology/oncology oriented,
# so blood/marrow/cancer vocabulary and everyday clinical terms matter most.
_BIAS_PRIORITY = [
    "symptoms",
    "conditions",
    "medications",
    "labs",
    "oncology",
    "procedures",
    "anatomy",
    "vitals",
    "history",
    "plan",
    "specialty",
    "obstetric",
]

# Maximum Persian terms handed to ASR biasing (kept well under the whisper
# prompt window; asr_context enforces the hard caps).
MAX_ASR_BIAS_TERMS = 80

# Hard cap on how many terms the refinement reference table will list.
MAX_CONTEXT_TERMS = 50

_WS = re.compile(r"\s+")


@lru_cache(maxsize=1)
def load_terms() -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    """Load every term once.

    Returns:
        (fa_to_en, en_to_fa, all_entries)
          fa_to_en: normalised Persian term -> English (first match wins)
          en_to_fa: normalised English term -> Persian (first match wins)
          all_entries: the raw entry dicts (fa, en, cat)
    """
    fa_to_en: dict[str, str] = {}
    en_to_fa: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    if not TERMS_DIR.is_dir():
        logger.warning("medical terms directory missing: %s", TERMS_DIR)
        return fa_to_en, en_to_fa, entries
    for path in sorted(TERMS_DIR.glob("*.json")):
        try:
            data = __import__("json").loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - never fatal to a pipeline
            logger.warning("skipping corrupt term file %s: %s", path.name, e)
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            fa = str(entry.get("fa", "")).strip()
            en = str(entry.get("en", "")).strip()
            cat = str(entry.get("cat", "")).strip()
            if not fa or not en:
                continue
            norm_fa = _normalise(fa)
            norm_en = _normalise(en).lower()
            record: dict[str, Any] = {"fa": fa, "en": en, "cat": cat}
            # Optional provenance fields (W2.4); older JSON without them is
            # fully backward-compatible.
            src = entry.get("src")
            if isinstance(src, str) and src.strip():
                record["src"] = src.strip()
            icd10 = entry.get("icd10")
            if isinstance(icd10, str) and icd10.strip():
                record["icd10"] = icd10.strip()
            variants = entry.get("variants")
            if isinstance(variants, list):
                clean = [v.strip() for v in variants if isinstance(v, str) and v.strip()]
                if clean:
                    record["variants"] = clean
            entries.append(record)
            fa_to_en.setdefault(norm_fa, en)
            en_to_fa.setdefault(norm_en, fa)
    logger.info("Loaded %d medical terms from %s", len(entries), TERMS_DIR.name)
    return fa_to_en, en_to_fa, entries


def _normalise(text: str) -> str:
    """Normalise whitespace and drop the ZWNJ used inside Persian words so
    matching is not defeated by zero-width-joiner spacing."""
    return _WS.sub(" ", text.replace("\u200c", "")).strip()


def search(query: str, limit: int = 10, threshold: int = 55) -> list[dict[str, Any]]:
    """Fuzzy bilingual search over the dictionary.

    Returns a list of ``{"fa", "en", "cat", "score", "side"}`` sorted by
    score (0-100) descending. ``side`` records which field the best match was
    against ("fa" or "en") so callers can phrase their answer.
    """
    q = (query or "").strip()
    if not q:
        return []
    _fa, _en, entries = load_terms()
    if not entries:
        return []

    fuzz: Any | None = None
    try:
        from rapidfuzz import fuzz as _fuzz_module

        fuzz = _fuzz_module
    except Exception:  # pragma: no cover - rapidfuzz is a hard dependency
        fuzz = None

    q_norm = _normalise(q).lower()
    scored: list[dict[str, Any]] = []

    def _side_score(side: str) -> tuple[float, int]:
        """Score ``q_norm`` against one term side; returns (score, side_len).

        Exact match wins outright. Containment only counts when the shorter
        string is at least 4 chars, so 2-3 char terms/queries (قلب, AF, INR)
        do not light up half the dictionary via partial matches.
        """
        if q_norm == side:
            return 100.0, len(side)
        if fuzz is None:
            return (92.0 if (q_norm in side or side in q_norm) else 0.0), len(side)
        score = max(fuzz.ratio(q_norm, side), fuzz.token_sort_ratio(q_norm, side))
        min_len = min(len(q_norm), len(side))
        if min_len >= 4:
            contained = q_norm in side or side in q_norm
        elif min_len >= 2 and q_norm.isascii() and side.isascii():
            # Short Latin acronym (LDH, INR, PE, CT...): must appear as a
            # whole word, so "pe" matches "pulmonary embolism (PE)" but not
            # "...topenic purpura".
            short, long_ = (q_norm, side) if len(q_norm) <= len(side) else (side, q_norm)
            contained = (
                re.search(r"(?<![a-z0-9])" + re.escape(short) + r"(?![a-z0-9])", long_) is not None
            )
        else:
            # Short Persian tokens (قلب, گرم) never get a containment boost:
            # 2-3 char words would light up whole categories.
            contained = False
        if contained:
            score = max(score, 92.0)
        return float(score), len(side)

    for e in entries:
        fa_n = _normalise(e["fa"]).lower()
        en_n = _normalise(e["en"]).lower()
        fa_score, fa_len = _side_score(fa_n)
        en_score, en_len = _side_score(en_n)
        if (fa_score, fa_len) >= (en_score, en_len):
            best, side, best_len = fa_score, "fa", fa_len
        else:
            best, side, best_len = en_score, "en", en_len
        if best >= threshold:
            scored.append(
                {
                    "fa": e["fa"],
                    "en": e["en"],
                    "cat": e["cat"],
                    "score": round(best, 1),
                    "side": side,
                    "_len": best_len,
                }
            )

    # Higher score first; on ties the longer (more specific) match wins.
    scored.sort(key=lambda s: (s["score"], s["_len"], s["en"]), reverse=True)
    return [{k: v for k, v in s.items() if k != "_len"} for s in scored[: max(1, int(limit))]]


@lru_cache(maxsize=8192)
def _word_re(term_norm: str) -> re.Pattern:
    """Whole-word pattern on ZWNJ-stripped, casefolded text.

    Persian letters are ``\\w``, so ``(?<!\\w)…(?!\\w)`` gives Persian-aware
    word boundaries: a 2-char term never matches inside a longer word.
    """
    return re.compile(r"(?<!\w)" + re.escape(term_norm) + r"(?!\w)")


def _count_word_occurrences(term_norm: str, text_norm: str) -> int:
    """Whole-word occurrence count (substring test first as a fast path)."""
    if len(term_norm) < 2 or term_norm not in text_norm:
        return 0
    return len(_word_re(term_norm).findall(text_norm))


def _provenance_rank(entry: dict[str, Any]) -> int:
    """Curated-tier entries (inn/fda/curated/unset) outrank generated ones."""
    return 0 if entry.get("src") == "generated" else 1


def terms_for_context(text: str, max_terms: int = MAX_CONTEXT_TERMS) -> list[dict[str, Any]]:
    """Find dictionary terms that occur in ``text`` (either language).

    Matching is whole-word on ZWNJ-normalized, casefolded text with a
    minimum term length of 2 — mirroring ``search()``'s short-term guards,
    so 2-3 char terms no longer light up inside longer words. Ordering:
    curated-tier provenance first, then longer (more specific) matches,
    then frequency. Returns ``[{"fa", "en", "cat", "occurrences"}]`` capped
    at ``max_terms``.
    """
    if not text:
        return []
    _fa, _en, entries = load_terms()
    if not entries:
        return []
    t_norm = _normalise(text).lower()
    matches: list[dict[str, Any]] = []
    for e in entries:
        fa_n = _normalise(e["fa"]).lower()
        en_n = _normalise(e["en"]).lower()
        occ = _count_word_occurrences(fa_n, t_norm) + _count_word_occurrences(en_n, t_norm)
        if occ > 0:
            item: dict[str, Any] = {
                "fa": e["fa"],
                "en": e["en"],
                "cat": e["cat"],
                "occurrences": occ,
                "_len": max(len(fa_n), len(en_n)),
                "_src_rank": _provenance_rank(e),
            }
            if e.get("src"):
                item["src"] = e["src"]
            matches.append(item)
    # Curated before generated; then more specific (longer); then frequency.
    matches.sort(key=lambda m: (m["_src_rank"], m["_len"], m["occurrences"], m["en"]), reverse=True)
    out = []
    seen: set[tuple[str, str]] = set()
    for m in matches:
        key = (m["fa"].casefold(), m["en"].casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append({k: v for k, v in m.items() if not k.startswith("_")})
        if len(out) >= max_terms:
            break
    return out


def asr_bias_terms(max_terms: int = MAX_ASR_BIAS_TERMS) -> list[str]:
    """High-value Persian terms for ASR biasing, in category priority order."""
    _fa, _en, entries = load_terms()
    if not entries:
        return []
    by_cat: dict[str, list[str]] = {}
    for e in entries:
        by_cat.setdefault(e["cat"], []).append(e["fa"])
    terms: list[str] = []
    seen: set[str] = set()
    for cat in _BIAS_PRIORITY:
        for term in by_cat.get(cat, []):
            key = _normalise(term).casefold()
            if term and key not in seen:
                seen.add(key)
                terms.append(term)
        if len(terms) >= max_terms:
            break
    return terms[:max_terms]


def format_lookup_results(query: str, matches: list[dict[str, Any]]) -> str:
    """Render search results as a readable block for the LLM to answer from."""
    if not matches:
        return (
            f"No medical-term match found for '{query}'. "
            "If this is a term lookup, say the dictionary has no entry for it and "
            "suggest the closest related term only if you are confident."
        )
    lines = [f"Medical dictionary matches for '{query}':"]
    for m in matches:
        lines.append(f"• {m['fa']}  ⇄  {m['en']}  [{m['cat']}]  (match {m['score']})")
    lines.append(
        "Answer the user's question using these standard Persian-English pairs. "
        "If the user wrote in Persian, give the English term; if in English, give "
        "the Persian term. Keep it concise."
    )
    return "\n".join(lines)


def terminology_reference_block(text: str, max_terms: int = MAX_CONTEXT_TERMS) -> str:
    """Build the refinement-prompt terminology reference for a draft.

    The block is designed to be appended AFTER the "no terminology changes"
    guardrail: it re-opens that rule as a scoped exception limited to surface
    form (transliteration / English spelling → standard Persian), so the two
    instructions cannot be read as contradictory. Returns "" when nothing
    matches, so callers can simply concatenate.
    """
    matches = terms_for_context(text, max_terms=max_terms)
    if not matches:
        return ""
    lines = [
        "جدول واژگان استاندارد این متن (فارسی ⇄ انگلیسی):",
    ]
    for m in matches:
        lines.append(f"- {m['fa']} ⇄ {m['en']}")
    lines.append(
        "استثنای محدود روی قاعدهٔ «اصطلاحات را تغییر ندهید»: اگر اصطلاح بالینی "
        "این جدول با املای ترنس‌لترهٔ غیراستاندارد یا به‌صورت انگلیسی در متن ورودی "
        "آمده، آن را به شکل استاندارد فارسی جدول تطبیق دهید. این تنها تغییری است "
        "که بر اصطلاحات مجاز است؛ معنا، اعداد، واحدها، دوزها و نفی‌ها را هرگز "
        "تغییر ندهید و اصطلاحی که در جدول نیست را دست نزنید."
    )
    return "\n".join(lines)
