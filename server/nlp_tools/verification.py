"""Deterministic post-generation faithfulness verification for clinical notes.

Compares a generated clinical note against the source transcript it was
generated from, using LLM-free string analysis. Catches the failure modes
that matter most in a documentation context:

* ``number_drift``       — a number (or number+unit) in the note that the source
                           does not contain
* ``unit_mismatch``      — the same number carries a different unit in the note
                           ("۵۰ میلی‌گرم" vs "۵۰۰ گرم")
* ``negation_flip``      — a finding negated in the source ("درد شکم ندارد")
                           is stated affirmatively in the note for the same
                           predicate
* ``ungrounded_term``    — a dictionary-known drug/lab/condition/oncology term
                           in the note that the source does not contain
* ``low_overlap_sentence`` — a note sentence with almost no lexical connection
                           to the source (the classic fabrication signature)

Design rules (deliberate):

* **Flag-only, never edit.** Findings surface as review warnings for the
  clinician; nothing is blocked and nothing is rewritten automatically.
* **Conservative.** When in doubt, stay silent: a false positive erodes
  clinician trust, while a missed flag is covered by the clinician's own
  review. Predicate-scoped negation checks and word-boundary term matching
  are intentionally stricter than substring matching.
* **Digit-insensitive.** Persian ۰-۹, Arabic-Indic ٠-٩ and ASCII digits are
  unified before comparison, so "7.2" vs "۷٫۲" is the same value.
* **Stdlib-only at import time.** This module is loaded by the stdlib-only
  nightly precision gate (via ``server.bench.guards``) on a bare runner, so
  no third-party imports are allowed at module level. The medical dictionary
  is imported lazily and degrades to "no term checks" when unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Number normalisation
# --------------------------------------------------------------------------

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# Bullet / list markers such as "۱." or "2-" at the start of a line: numbers
# used for numbering, not clinical values. The report format itself is
# "ترجیحاً شماره‌دار", so bare list ordinals must not count as number drift.
_BULLET_MARKER_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})[.)\-\u2010\u2011]")


def strip_zwnj(text: str | None) -> str:
    """Remove ZWNJ (نیم‌فاصله) — semantic in Persian prose, irrelevant for matching."""
    return (text or "").replace("\u200c", "")


def normalise_numbers(text: str | None) -> str:
    """Unify digit scripts and decimal separators for value comparison.

    Persian/Arabic-Indic digits become ASCII; the Arabic decimal separator
    (٫) and a Persian comma between digits (7،2) become ``.``.
    """
    if not text:
        return text or ""
    text = text.translate(_PERSIAN_DIGITS).translate(_ARABIC_INDIC_DIGITS)
    text = text.replace("\u066b", ".")
    text = re.sub(r"(?<=\d)،(?=\d)", ".", text)
    return text


def extract_numbers(text: str | None) -> set[str]:
    """All numeric values in ``text`` (digit-normalised), list markers included."""
    return set(_NUMBER_RE.findall(normalise_numbers(text or "")))


def _bullet_marker_numbers(text: str | None) -> set[str]:
    # Normalised so "۱." in the note compares equal to "1" from extract_numbers.
    return {normalise_numbers(m) for m in _BULLET_MARKER_RE.findall(text or "")}


# --------------------------------------------------------------------------
# Number + unit pairs
# --------------------------------------------------------------------------

# (surface unit, canonical unit). Surface forms are matched on
# ZWNJ-stripped, lower-cased text, so "میلی‌گرم" and "میلیگرم" both appear.
# Latin/Persian synonyms of the same measurement share one canonical key so a
# legitimate script change ("mg" -> "میلی‌گرم") is not flagged, while a true
# unit change ("mg" -> "g") is.
_UNIT_ALIASES: tuple[tuple[str, str], ...] = (
    ("mg", "mg"),
    ("میلیگرم", "mg"),
    ("mcg", "mcg"),
    ("µg", "mcg"),
    ("μg", "mcg"),
    ("میکروگرم", "mcg"),
    ("kg", "kg"),
    ("کیلوگرم", "kg"),
    ("g", "g"),
    ("گرم", "g"),
    ("ml", "ml"),
    ("میلیلیتر", "ml"),
    ("l", "l"),
    ("لیتر", "l"),
    ("%", "percent"),
    ("٪", "percent"),
    ("درصد", "percent"),
    ("mmol", "mmol"),
    ("mmhg", "mmhg"),
    ("bar", "bar"),
    ("bpm", "bpm"),
    ("روز", "day"),
    ("ساعت", "hour"),
    ("هفته", "week"),
    ("ماه", "month"),
    ("سال", "year"),
    ("قطره", "drop"),
    ("قرص", "tablet"),
    ("امپول", "ampoule"),
    ("بار", "times"),
    ("بر", "ratio"),
)


def _unit_pattern() -> re.Pattern:
    units = sorted({u for u, _ in _UNIT_ALIASES}, key=len, reverse=True)
    return re.compile(r"(\d+(?:\.\d+)?)\s*(" + "|".join(re.escape(u) for u in units) + r")\b")


_UNIT_PATTERN = _unit_pattern()
_UNIT_CANON: dict[str, str] = dict(_UNIT_ALIASES)


def extract_number_units(text: str | None) -> dict[str, set[str]]:
    """Map each numeric value in ``text`` to the set of canonical units it carries."""
    out: dict[str, set[str]] = {}
    if not text:
        return out
    t = strip_zwnj(text).lower()
    for match in _UNIT_PATTERN.finditer(t):
        number, unit = match.group(1), match.group(2)
        out.setdefault(number, set()).add(_UNIT_CANON[unit])
    return out


# --------------------------------------------------------------------------
# Number drift
# --------------------------------------------------------------------------


def detect_number_drift(source: str, generated: str) -> list[str]:
    """Numbers present in ``generated`` but absent from ``source``.

    Bare list ordinals at line starts ("۱.", "2-") are excluded: they are
    numbering, not clinical values.
    """
    if not source or not generated:
        return []
    drifted = extract_numbers(generated) - extract_numbers(source)
    drifted -= _bullet_marker_numbers(generated)
    return sorted(drifted)


def detect_unit_mismatch(source: str, generated: str) -> list[str]:
    """Numbers whose unit in ``generated`` differs from ``source``.

    Returns issues formatted as ``"<number> <note_unit> (source: <units>)"``.
    Synonym units (mg / میلی‌گرم) compare equal via the canonical key.
    """
    if not source or not generated:
        return []
    src_units = extract_number_units(source)
    issues: list[str] = []
    for number, units in sorted(extract_number_units(generated).items()):
        known = src_units.get(number)
        if known is None:
            continue  # the number itself is new -> number_drift covers it
        for unit in sorted(units):
            if unit not in known:
                issues.append(f"{number} {unit} (source: {', '.join(sorted(known))})")
    return issues


# --------------------------------------------------------------------------
# Negation flips (predicate-scoped)
# --------------------------------------------------------------------------

# Verb-form negations: the predicate is what PRECEDES them ("درد شکم ندارد").
_VERB_NEGATION_MARKERS = frozenset(
    {
        "ندارد",
        "نداشت",
        "ندارند",
        "نداشته",
        "نداشتند",
        "نداشتیم",
        "نداریم",
        "نبود",
        "نبودی",
        "نبوده",
        "نبودند",
        "نیست",
        "نیستند",
        "نیستیم",
        "نمیکند",
        "نمیکرد",
        "نکرد",
        "نکردند",
        "نمیشود",
        "نشد",
        "نشده",
        "نشود",
        "نشدند",
        "نمیداند",
        "نمیبیند",
        "نمیخواهد",
        "نمیپذیرد",
        "نمیسازد",
        "ندید",
        "ندیدم",
        "ندیدند",
        "ندیده",
    }
)
# "بدون" negates what FOLLOWS ("بدون گره تروئید"): it suppresses a flip on the
# note side but never generates a predicate from the tokens before it (those
# tokens are an unrelated phrase, e.g. "بدون تنگی نفس" must not negate "آلرژی").
_BEFORE_NEGATION_MARKERS = frozenset({"بدون"})
# Any token that, adjacent to a predicate in the note, marks it as negated.
_NEGATION_MARKERS = _VERB_NEGATION_MARKERS | _BEFORE_NEGATION_MARKERS

_STOPWORDS = frozenset(
    {
        "با",
        "به",
        "بر",
        "در",
        "از",
        "روی",
        "برای",
        "و",
        "که",
        "را",
        "نیز",
        "هم",
        "این",
        "یک",
        "بعد",
        "قبل",
        "اما",
        "ولی",
        "یا",
        "اگر",
        "همچنین",
    }
)

_PUNCT_RE = re.compile(r"[،؛.!?؟٪%\(\)\[\]«»\"'’‘،؛:：]+")


def _clean_token(token: str) -> str:
    return _PUNCT_RE.sub("", strip_zwnj(token)).strip().lower()


def _tokens(text: str) -> list[str]:
    return [_clean_token(t) for t in (text or "").split()]


def _negated_predicates(text: str) -> list[str]:
    """Predicates that are negated in ``text``.

    For each negation marker, take up to three significant tokens before it
    (stopwords and digits removed). A single-token predicate must be at least
    five characters — shorter ones ("تب", "درد") are too generic and cause
    false positives when the same generic word is affirmed elsewhere.
    """
    tokens = _tokens(text)
    preds: list[str] = []
    for i, tok in enumerate(tokens):
        if not tok or tok not in _VERB_NEGATION_MARKERS:
            continue
        window = list(tokens[max(0, i - 3) : i])
        window = [t for t in window if t and t not in _STOPWORDS and not t.isdigit()]
        if not window:
            continue
        if len(window) == 1 and len(window[0]) < 5:
            continue
        preds.append(" ".join(window[-3:]))
    return sorted(set(preds))


def detect_negation_flip(source: str, generated: str) -> list[str]:
    """Negated findings in ``source`` stated affirmatively in ``generated``.

    Predicate-scoped: "درد قفسه سینه ندارد" in the source is only a flip if
    the predicate itself re-appears in the note without a nearby negation
    marker. Affirming a *different* predicate ("درد شکم دارد" alongside a
    negated "درد قفسه سینه") is a different (omission) problem and is not
    flagged here.
    """
    if not source or not generated:
        return []
    gen_tokens = _tokens(generated)
    flips: list[str] = []
    for pred in _negated_predicates(source):
        pred_tokens = pred.split()
        width = len(pred_tokens)
        for j in range(len(gen_tokens) - width + 1):
            if gen_tokens[j : j + width] == pred_tokens:
                before = gen_tokens[j - 1] if j > 0 else ""
                following = gen_tokens[j + width : j + width + 3]
                if before in _NEGATION_MARKERS or any(
                    tok in _NEGATION_MARKERS for tok in following
                ):
                    continue  # negation preserved in the note
                flips.append(pred)
                break
    return sorted(set(flips))


# --------------------------------------------------------------------------
# Ungrounded clinical terms (dictionary-grounded, lazy import)
# --------------------------------------------------------------------------

# Only high-stakes categories: a reworded symptom is tolerable, an invented
# drug or lab value is not. General words that are dictionary terms in other
# categories (سابقه, معاینه, ارجاع, فشار خون, ...) must never flag.
_TERM_CATEGORIES = frozenset({"medications", "labs", "conditions", "oncology"})

_TERM_INDEX_CACHE: list[tuple[str, str, str]] | None = None


def _term_index() -> list[tuple[str, str, str]]:
    """(normalised_term, display_term, category) for high-stakes categories.

    Both sides of each pair (Persian and English) are indexed; the English
    side matters because the product rule keeps drug names in Latin.
    Returns an empty list when the dictionary is unavailable (fail-open).
    """
    global _TERM_INDEX_CACHE
    if _TERM_INDEX_CACHE is not None:
        return _TERM_INDEX_CACHE
    entries: list[tuple[str, str, str]] = []
    try:
        from server.data.medical_dictionary import load_terms

        _fa, _en, raw = load_terms()
        seen: set[str] = set()
        for e in raw:
            if e.get("cat") not in _TERM_CATEGORIES:
                continue
            for side, display in (
                (e.get("fa", ""), e.get("fa", "")),
                (e.get("en", ""), e.get("en", "")),
            ):
                norm = strip_zwnj(str(side)).casefold().strip()
                if len(norm) < 2 or norm in seen:
                    continue
                seen.add(norm)
                entries.append((norm, str(display).strip(), str(e.get("cat", ""))))
    except Exception:  # noqa: BLE001 — verification must never break the report
        entries = []
    _TERM_INDEX_CACHE = entries
    return entries


def extract_clinical_terms(text: str | None) -> set[str]:
    """Display forms of high-stakes dictionary terms occurring in ``text``.

    Word-boundary matching on ZWNJ-stripped, case-folded text, so
    "آموکسی‌سیلین" matches "اموکسيسيلین" and "amoxicillin" does not match
    inside "amoxicillin clavulanate".
    """
    if not text:
        return set()
    t = strip_zwnj(text).casefold()
    found: set[str] = set()
    for norm, display, _cat in _term_index():
        if norm not in t:
            continue
        pattern = r"(?<!\w)" + re.escape(norm) + r"(?!\w)"
        if re.search(pattern, t):
            found.add(display)
    return found


def detect_ungrounded_terms(source: str, generated: str) -> list[str]:
    """High-stakes terms in ``generated`` that ``source`` does not contain."""
    if not source or not generated:
        return []
    return sorted(extract_clinical_terms(generated) - extract_clinical_terms(source))


# --------------------------------------------------------------------------
# Low-overlap sentences (fabrication signature)
# --------------------------------------------------------------------------

_FAB_TOKEN_RE = re.compile(r"[A-Za-z0-9؀-ۿ]{2,}")
_SENTENCE_RE = re.compile(r"[.\n؛]+")


def _fab_tokens(text: str) -> set[str]:
    # ZWNJ stripped first: "توصیه‌ها" is one word, not two tokens.
    return {m.group(0).lower() for m in _FAB_TOKEN_RE.finditer(strip_zwnj(text or ""))}


def detect_fabrication(source: str, generated: str) -> list[str]:
    """Note sentences whose content is not grounded in ``source``.

    A sentence with fewer than two content tokens is ignored (section
    headers). Overlap is measured on lower-cased tokens; the threshold is
    deliberately low (25%) so only near-total fabrications flag.
    """
    if not source or not generated:
        return []
    source_tokens = _fab_tokens(source)
    issues: list[str] = []
    for sentence in _SENTENCE_RE.split(generated):
        sentence = sentence.strip()
        tokens = _fab_tokens(sentence)
        if len(tokens) < 2:
            continue
        overlap = tokens & source_tokens
        if len(overlap) / len(tokens) < 0.25:
            issues.append(sentence)
    return issues


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One review-worthy faithfulness issue (never a blocking error)."""

    kind: (
        str  # number_drift | unit_mismatch | negation_flip | ungrounded_term | low_overlap_sentence
    )
    detail: str  # human-readable, Persian
    span: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "detail": self.detail, "span": self.span}


@dataclass
class VerificationResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def warnings(self) -> list[dict[str, str]]:
        return [f.as_dict() for f in self.findings]


def verify_note(source: str, generated: str) -> VerificationResult:
    """Run all faithfulness checks and aggregate deduplicated findings."""
    findings: list[Finding] = []

    for number in detect_number_drift(source, generated):
        findings.append(
            Finding(
                kind="number_drift",
                detail=f"عدد {number} در یادداشت هست ولی در متن ورودی نیامده است",
                span=number,
            )
        )
    for issue in detect_unit_mismatch(source, generated):
        findings.append(
            Finding(
                kind="unit_mismatch",
                detail=f"واحد یکی از اعداد در یادداشت با متن ورودی مطابقت ندارد: {issue}",
                span=issue,
            )
        )
    for pred in detect_negation_flip(source, generated):
        findings.append(
            Finding(
                kind="negation_flip",
                detail=f"«{pred}» در متن ورودی منفی ذکر شده بود ولی در یادداشت مثبت بیان شده است",
                span=pred,
            )
        )
    for term in detect_ungrounded_terms(source, generated):
        findings.append(
            Finding(
                kind="ungrounded_term",
                detail=f"اصطلاح «{term}» در یادداشت هست ولی در متن ورودی نیامده است",
                span=term,
            )
        )
    for sentence in detect_fabrication(source, generated):
        findings.append(
            Finding(
                kind="low_overlap_sentence",
                detail=f"این جمله در یادداشت پیوند کمی با متن ورودی دارد: «{sentence[:100]}»",
                span=sentence[:100],
            )
        )

    seen: set[tuple[str, str]] = set()
    deduped: list[Finding] = []
    for f in findings:
        key = (f.kind, f.span)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    return VerificationResult(deduped)
