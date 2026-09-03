"""Post-generation verification of note content against the transcript.

Plan refs B1 (quote validation) and A6 (numeric / negation tracing).
See docs/phlox-accuracy-hallucination-plan.md.

The verifier deliberately does NOT judge clinical quality and does NOT call
an LLM: every check here is deterministic string work over data the app
already has (the transcript and the generated fields). Deterministic checks
catch the two highest-yield hallucination classes measured in the literature
— fabricated content absent from the transcript, and corrupted numbers or
flipped negations — at zero cost and zero new hallucination risk.

Policy: findings are *flags surfaced to the clinician*, not silent edits.
The strict mode (``PHLOX_VERIFY_MODE=strict``) removes clearly unsupported
draft bullets before refinement; the default mode keeps everything and
attaches the report so the UI can amber-mark what needs review.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- config

# Fraction of a bullet's word trigrams (or a direct substring match) required
# to consider it transcript-supported. 0.85 is deliberately permissive: this
# is a *review trigger*, not an autograder.
_QUOTE_SUPPORT_THRESHOLD = float(os.environ.get("PHLOX_QUOTE_THRESHOLD", "0.85"))

# "flag" (default): keep all content, attach report. "strict": also drop
# unsupported draft bullets before refinement.
_VERIFY_MODE = (os.environ.get("PHLOX_VERIFY_MODE") or "flag").strip().lower()


def verify_mode() -> str:
    return _VERIFY_MODE if _VERIFY_MODE in {"flag", "strict"} else "flag"


# ---------------------------------------------------------------- text norm

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_LATIN = "0123456789"

# Folding rules: keep Arabic/Persian script variants interchangeable so
# provider Unicode differences never look like content changes.
_FOLD = str.maketrans(
    {
        **{c: _LATIN[i % 10] for i, c in enumerate(_PERSIAN_DIGITS + _ARABIC_DIGITS)},
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "ى": "ی",
        "،": " ",
        "؛": " ",
        "؟": " ",
        "٫": ".",
        "٬": ",",
    }
)

_NONWORD_RE = re.compile(r"[^0-9a-z.\u0600-\u06ff ]+", re.UNICODE)
# A dot only counts as a decimal separator when flanked by digits; the
# placeholder keeps it through the punctuation sweep. Thousands commas are
# removed outright so "1,200" and "1200" canonicalize identically.
_SENTENCE_DOT_RE = re.compile(r"(?<!\d)\.(?!\d)")
_THOUSANDS_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_WS_RE = re.compile(r" +")


def normalize_for_match(text: str) -> str:
    """Lowercase, fold digit/punct variants, strip diacritics and ZWNJ."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if not unicodedata.combining(c))
    t = t.translate(_FOLD)
    t = t.replace("\u200c", " ")  # ZWNJ splits Persian compounds; treat as space
    t = t.replace("\u200b", " ").replace("\xa0", " ")
    t = t.lower()
    t = _THOUSANDS_COMMA_RE.sub("", t)
    t = _SENTENCE_DOT_RE.sub(" ", t)
    t = _NONWORD_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip()


# ---------------------------------------------------------------- numbers

# Numeric token: digits with optional Persian/English decimal separator and
# thousands groups, with an optional unit glued or separated (mg, ml, mcg, g,
# IU, mmHg, %, بار/روز/هفته/ماه/سال ...).
_NUMBER_TOKEN_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?",
)
_UNIT_AFTER = re.compile(
    r"^(?:\s?(?:میلی\s?گرم|میکروگرم|mcg|mg|ml|میلی\s?لیتر|lit(?:er|re)|l|g|kg|cc|iu|واحد|unit(?:s)?|mmhg|درصد|%|بار در روز|بار/روز|بار در هفته|بار در ماه|روزانه|daily|bid|tid|qid|prn|mg/day|mg/dl|mmol/l|ng/ml))",
    re.IGNORECASE,
)


def _canonical_number(raw: str) -> str:
    value = raw.replace(",", "")
    if "." in value:
        try:
            f = float(value)
            if f == int(f):
                return str(int(f))
            return repr(f).rstrip("0").rstrip(".")
        except ValueError:
            return value
    return value


def extract_numbers(text: str) -> list[dict[str, Any]]:
    """Numeric facts (value + attached unit when adjacent) from text."""
    norm = normalize_for_match(text)
    out: list[dict[str, Any]] = []
    for m in _NUMBER_TOKEN_RE.finditer(norm):
        unit_m = _UNIT_AFTER.match(norm[m.end() : m.end() + 14])
        out.append(
            {
                "value": _canonical_number(m.group(0)),
                "unit": unit_m.group(0).strip() if unit_m else None,
                "context": norm[max(0, m.start() - 18) : m.end() + 14].strip(),
            }
        )
    return out


def number_mismatches(point: str, transcript_values: set[str], transcript_norm: str) -> list[str]:
    """Numbers present in a note bullet but absent from the transcript.

    Comparison is on canonical decimal values, so "40.0", "40" and "۴۰"
    are all equal after normalisation; the fallback scan covers the case
    where digits exist but a provider's thousands grouping differs.
    """
    problems: list[str] = []
    for num in extract_numbers(point):
        if num["value"] in transcript_values:
            continue
        if num["value"] and re.search(rf"(?<!\d){re.escape(num['value'])}(?!\d)", transcript_norm):
            continue
        problems.append(num["value"])
    return problems


# ---------------------------------------------------------------- negations

# High-precision negation cues. Ambiguous cues ("بدون", "بی") are included
# because the check only *raises a review flag*, and only when a whole
# clinical phrase that the transcript negates is asserted elsewhere.
_NEGATION_CUES = (
    "نیست",
    "نبود",
    "ندارد",
    "نکرد",
    "نشد",
    "نمی",
    "منفی",
    "بدون",
    "هیچ",
    "انکار",
    "رد کرد",
    "عدم",
    "ممنوع",
    "طبیعی بود",
    "not",
    "no",
    "denies",
    "denied",
    "without",
    "never",
    "negative",
    "ruled out",
    "resolved",
)

_CLAUSE_SPLIT_RE = re.compile(r"[\n.!?;!]")


def _make_cue_matcher(cues: tuple[str, ...]):
    """Word-boundary matching for Latin cues, substring matching for Persian.

    A plain substring test for "no" would match "not documented", "note",
    "protocol"; \b needs ASCII word characters, which Persian lacks, so the
    scripts are handled differently on purpose.
    """
    ascii_cues = [c for c in cues if c.isascii()]
    other_cues = [c for c in cues if not c.isascii()]
    ascii_re = (
        re.compile(r"(?:" + "|".join(re.escape(c) for c in ascii_cues) + r")")
        if ascii_cues
        else None
    )

    def has_cue(clause: str) -> bool:
        if any(c in clause for c in other_cues):
            return True
        if ascii_re is not None:
            for m in ascii_re.finditer(clause):
                before = clause[m.start() - 1] if m.start() else " "
                after = clause[m.end()] if m.end() < len(clause) else " "
                if not (before.isalnum() or after.isalnum()):
                    return True
        return False

    return has_cue


_has_negation_cue = _make_cue_matcher(_NEGATION_CUES)


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT_RE.split(text) if c.strip()]


def _content_words(clause: str) -> set[str]:
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "with",
        "for",
        "was",
        "were",
        "is",
        "are",
        "patient",
        "بیمار",
        "همچنین",
        "کلی",
        "در",
        "به",
        "از",
        "با",
        "که",
        "این",
        "آن",
        "had",
        "has",
        "of",
        "on",
    }
    return {w for w in clause.split() if len(w) >= 3 and w not in stop}


def negation_conflicts(points: list[str], transcript: str) -> list[dict[str, str]]:
    """Bullets asserting something the transcript explicitly negated.

    Deliberately conservative: requires at least two shared content words
    between the note clause and a negated transcript clause, and no
    negation cue in the note clause itself.
    """
    negated: list[tuple[set[str], str]] = []
    for clause in _clauses(normalize_for_match(transcript)):
        if _has_negation_cue(clause):
            words = _content_words(clause)
            if words:
                negated.append((words, clause))
    if not negated:
        return []

    conflicts: list[dict[str, str]] = []
    for point in points:
        for clause in _clauses(normalize_for_match(point)):
            if _has_negation_cue(clause):
                continue  # the note itself hedges/negates: fine
            words = _content_words(clause)
            if len(words) < 2:
                continue
            for neg_words, neg_clause in negated:
                shared = words & neg_words
                if len(shared) >= 2 and len(shared) >= 0.6 * len(words):
                    conflicts.append(
                        {
                            "point": point,
                            "transcript_clause": neg_clause,
                            "shared_terms": " ".join(sorted(shared)),
                        }
                    )
                    break
    return conflicts


# ---------------------------------------------------------------- quotes


def quote_support(point: str, transcript_norm: str, trigrams: set[tuple[str, str, str]]) -> float:
    """0..1 support score for one note bullet against the transcript.

    Word-trigram containment after Unicode normalisation: every three-word
    window of the bullet must have been spoken. The measure is asymmetric on
    purpose — an LLM *appending* a plausible extra fact lowers the score even
    though every other word appears, which is precisely the fabrication
    shape the clinical-safety literature reports. (Symmetric ratios such as
    partial-ratio would rate that as full support.)
    """
    p = normalize_for_match(point)
    if not p:
        return 1.0
    if p in transcript_norm:
        return 1.0
    tokens = p.split()
    if len(tokens) < 3:
        return 0.4
    hits = sum(1 for i in range(len(tokens) - 2) if tuple(tokens[i : i + 3]) in trigrams)
    return hits / (len(tokens) - 2)


def _build_trigrams(transcript_norm: str) -> set[tuple[str, str, str]]:
    words = transcript_norm.split()
    return {tuple(words[i : i + 3]) for i in range(max(0, len(words) - 2))}  # type: ignore[misc]


# ---------------------------------------------------------------- bullet utils


def split_bullets(content: str) -> list[str]:
    """Split a formatted field content into individual bullet strings."""
    lines = [line.strip() for line in content.splitlines()]
    return [re.sub(r"^[•*\-\d.)\s]+", "", line).strip() for line in lines if line.strip()]


def join_bullets(points: list[str]) -> str:
    if not points:
        return ""
    if all(p.startswith("•") for p in points):
        return "\n".join(points)
    return "\n".join(f"• {p}" for p in points)


# ---------------------------------------------------------------- orchestration


@dataclass
class VerificationReport:
    mode: str = "flag"
    quote_checked: int = 0
    unsupported: list[dict[str, Any]] = field(default_factory=list)
    number_problems: list[dict[str, Any]] = field(default_factory=list)
    negation_problems: list[dict[str, Any]] = field(default_factory=list)
    # Fields where the refinement pass drifted from the draft content and was
    # reverted to the draft (plan ref B6).
    refinement_reverts: list[dict[str, Any]] = field(default_factory=list)
    # Optional independent LLM entailment pass (plan ref B2).
    entailment: dict[str, Any] | None = None

    @property
    def flagged(self) -> bool:
        entailment_bad = bool(self.entailment and self.entailment.get("counts", {}).get("flagged"))
        return bool(
            self.unsupported or self.number_problems or self.negation_problems or entailment_bad
        )

    def to_dict(self) -> dict[str, Any]:
        if not (
            self.unsupported
            or self.number_problems
            or self.negation_problems
            or self.refinement_reverts
            or self.entailment
        ):
            return {}
        payload: dict[str, Any] = {
            "mode": self.mode,
            "quoteChecked": self.quote_checked,
            "unsupportedQuotes": self.unsupported[:12],
            "numberProblems": self.number_problems[:12],
            "negationProblems": [
                {
                    "field": n["field"],
                    "point": n["point"][:160],
                    "transcriptClause": n["transcript_clause"][:160],
                }
                for n in self.negation_problems[:12]
            ],
        }
        if self.refinement_reverts:
            payload["refinementReverts"] = self.refinement_reverts[:12]
        if self.entailment:
            payload["entailment"] = self.entailment
        return payload


def verify_draft(
    fields: dict[str, list[str]], transcript: str, mode: str | None = None
) -> tuple[dict[str, list[str]], VerificationReport]:
    """B1 quote check on extracted draft bullets, before refinement.

    Draft bullets are expected to be near-verbatim; paraphrase is introduced
    later by refinement and is checked for content drift by its own guards.
    Returns (possibly filtered in strict mode, fields, report).
    """
    report = VerificationReport(mode=(mode or verify_mode()).strip().lower())
    transcript_norm = normalize_for_match(transcript)
    trigrams = _build_trigrams(transcript_norm)
    kept_fields: dict[str, list[str]] = {}
    for key, points in fields.items():
        kept: list[str] = []
        for point in points:
            if not point.strip():
                continue
            report.quote_checked += 1
            score = quote_support(point, transcript_norm, trigrams)
            if score < _QUOTE_SUPPORT_THRESHOLD:
                report.unsupported.append(
                    {"field": key, "point": point[:200], "score": round(score, 2)}
                )
                if report.mode == "strict":
                    continue  # drop only in strict mode
            kept.append(point)
        kept_fields[key] = kept
    return kept_fields, report


def verify_final_fields(
    fields: dict[str, str], transcript: str, report: VerificationReport
) -> VerificationReport:
    """A6 numeric + negation trace on the final (refined) field contents."""
    transcript_norm = normalize_for_match(transcript)
    transcript_values = {f["value"] for f in extract_numbers(transcript)}
    for key, content in fields.items():
        if not content:
            continue
        bullets = split_bullets(content)
        for point in bullets:
            problems = number_mismatches(point, transcript_values, transcript_norm)
            for value in problems:
                report.number_problems.append({"field": key, "value": value, "point": point[:200]})
        for conflict in negation_conflicts(bullets, transcript):
            conflict["field"] = key
            report.negation_problems.append(conflict)
    return report


def verify_note(fields: dict[str, str], transcript: str) -> VerificationReport:
    """Standalone verification of final fields (used by reprocess/save paths)."""
    report = VerificationReport(mode=verify_mode())
    return verify_final_fields(fields, transcript, report)


def entity_drift(draft: str, refined: str) -> list[str]:
    """Content-preservation diff between a draft and its refined version.

    Refinement may reformat, never re-content: numbers that appeared or
    vanished and polarity flips (refined asserting what the draft negated,
    or vice versa) are returned as drift reasons (plan ref B6). Used to
    revert refinement on drift instead of shipping it.
    """
    problems: list[str] = []
    draft_values = {f["value"] for f in extract_numbers(draft)}
    refined_values = {f["value"] for f in extract_numbers(refined)}
    for value in sorted(refined_values - draft_values):
        problems.append(f"number_added:{value}")
    for value in sorted(draft_values - refined_values):
        problems.append(f"number_dropped:{value}")
    if negation_conflicts(split_bullets(refined), draft):
        problems.append("negation_flip")
    if negation_conflicts(split_bullets(draft), refined):
        problems.append("negation_added")
    return problems


def example_leakage(
    instruction: str, sources: list[str], min_tokens: int = 6, max_overlap: float = 0.6
) -> bool:
    """True when a generated instruction copies visit content from *sources*.

    Adaptive refinement instructions must be general style guidance; an
    instruction that quotes this encounter's content leaks patient detail
    into every future note (plan ref B7). Measured as word-trigram overlap,
    the same primitive the quote validator uses.
    """
    n = normalize_for_match(instruction)
    tokens = n.split()
    if len(tokens) < min_tokens:
        return False
    combined = normalize_for_match(" \n ".join(source for source in sources if source))
    trigrams = _build_trigrams(combined)
    hits = sum(1 for i in range(len(tokens) - 2) if tuple(tokens[i : i + 3]) in trigrams)
    return hits / (len(tokens) - 2) >= max_overlap
