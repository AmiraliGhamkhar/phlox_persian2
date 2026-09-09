"""Quality gate for the bundled Persian-English medical term data.

The term lists in ``server/data/terms/*.json`` feed the clinical surfaces
(ASR biasing, the workspace dictionary lookup, the report terminology
reference), so a corrupted or junky entry propagates to patient
documentation. This module validates structure and obvious quality problems
and is executed by the test suite (``server/tests/test_medical_dictionary.py``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TERMS_DIR = Path(__file__).parent / "terms"

REQUIRED_CATEGORIES = {
    "symptoms",
    "conditions",
    "medications",
    "procedures",
    "labs",
    "anatomy",
    "vitals",
    "history",
    "plan",
    "specialty",
    "oncology",
    "obstetric",
}

_PERSIAN_CHAR = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")
# Latin allowed in the Persian field only as well-known acronyms/digits.
_FA_ALLOWED_EXTRA = re.compile(r"^[\u0600-\u06FF\u0660-\u0669A-Za-z0-9\u200c \-/+().%]+$")
# Latin sequences that may legitimately appear inside a Persian term
# (virus letters, acronyms, unit-ish symbols). Longer Latin runs inside the
# Persian field are a corruption signal (e.g. 'اسکab') and fail validation.
_FA_LATIN_WHITELIST = {
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "K",
    "Rh",
    "IV",
    "CT",
    "MRI",
    "ECG",
    "EKG",
    "DNA",
    "RNA",
    "PCR",
    "HIV",
    "HBV",
    "HCV",
    "HBSAG",
    "HCC",
    "COPD",
    "GERD",
    "IBS",
    "IBD",
    "RA",
    "OA",
    "TIA",
    "DVT",
    "PE",
    "MI",
    "DKA",
    "CKD",
    "AKI",
    "CVD",
    "SLE",
    "PTSD",
    "GAD",
    "OCD",
    "PCOS",
    "BPH",
    "ALS",
    "CPK",
    "TSH",
    "FT4",
    "FT3",
    "INR",
    "PT",
    "aPTT",
    "CRP",
    "ESR",
    "ANA",
    "HLA",
    "IgA",
    "IgG",
    "IgM",
    "eGFR",
    "HbA1c",
    "CBC",
    "M",
    "ISS",
    "R",
    "S",
    "CRAB",
    "PSA",
    "PET",
}
_LATIN_RUN = re.compile(r"[A-Za-z]{1,}")
_WS = re.compile(r"\s{2,}")
_BAD_EN_PREFIX = re.compile(r"^(post- |the |a |an )")

# Optional provenance fields (W2.4). Missing fields stay valid forever —
# these checks only apply when a field is present.
ALLOWED_SOURCES = frozenset({"inn", "fda", "curated", "generated"})
_ICD10_RE = re.compile(r"^[A-Z][A-Z0-9]*(\.[A-Z0-9]+)?$")


class TermValidationError(ValueError):
    """A term file or entry failed quality validation."""


def load_raw_terms(terms_dir: Path | None = None) -> list[dict]:
    """Load all term entries from every ``*.json`` file (sorted by name)."""
    base = terms_dir or TERMS_DIR
    entries: list[dict] = []
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise TermValidationError(f"{path.name}: invalid JSON: {e}") from e
        if not isinstance(data, list):
            raise TermValidationError(f"{path.name}: expected a JSON array")
        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                raise TermValidationError(f"{path.name}[{i}]: entry is not an object")
            entry = dict(entry)
            entry["_file"] = path.name
            entry["_index"] = i
            entries.append(entry)
    return entries


def validate_terms(entries: list[dict] | None = None) -> list[dict]:
    """Validate term entries; returns the entries when clean, else raises."""
    if entries is None:
        entries = load_raw_terms()
    if not entries:
        raise TermValidationError("no term entries found")

    seen_pairs: set[tuple[str, str]] = set()
    fa_counts: dict[str, int] = {}
    en_counts: dict[str, int] = {}
    for e in entries:
        loc = f"{e.get('_file', '?')}#{e.get('_index', '?')}"
        fa = e.get("fa")
        en = e.get("en")
        cat = e.get("cat")

        if not isinstance(fa, str) or not fa.strip():
            raise TermValidationError(f"{loc}: field 'fa' missing or empty")
        if not isinstance(en, str) or not en.strip():
            raise TermValidationError(f"{loc}: field 'en' missing or empty")
        if not isinstance(cat, str) or not cat.strip():
            raise TermValidationError(f"{loc}: field 'cat' missing or empty")

        fa = fa.strip()
        en = en.strip()
        if fa != e["fa"] or en != e["en"]:
            raise TermValidationError(f"{loc}: leading/trailing whitespace")
        if _WS.search(fa) or "  " in en:
            raise TermValidationError(f"{loc}: multiple consecutive spaces")

        if not _PERSIAN_CHAR.search(fa):
            raise TermValidationError(f"{loc}: 'fa' has no Persian characters: {fa!r}")
        if not _FA_ALLOWED_EXTRA.match(fa):
            raise TermValidationError(f"{loc}: 'fa' contains unexpected characters: {fa!r}")
        for run in _LATIN_RUN.findall(fa):
            if run not in _FA_LATIN_WHITELIST:
                raise TermValidationError(
                    f"{loc}: unexpected Latin run {run!r} inside Persian term {fa!r}"
                )
        if _PERSIAN_CHAR.search(en):
            raise TermValidationError(f"{loc}: 'en' contains Persian characters: {en!r}")
        if not _LATIN.search(en):
            raise TermValidationError(f"{loc}: 'en' has no Latin characters: {en!r}")
        if _BAD_EN_PREFIX.match(en):
            raise TermValidationError(f"{loc}: 'en' starts with filler: {en!r}")
        if _WS.search(en):
            raise TermValidationError(f"{loc}: 'en' has irregular spacing: {en!r}")
        if len(fa) > 80 or len(en) > 120:
            raise TermValidationError(f"{loc}: entry too long (fa={fa!r})")

        if cat not in REQUIRED_CATEGORIES:
            raise TermValidationError(f"{loc}: unknown category {cat!r}")

        # Optional provenance fields — validated only when present.
        if "src" in e:
            src = e["src"]
            if not isinstance(src, str) or src not in ALLOWED_SOURCES:
                raise TermValidationError(
                    f"{loc}: field 'src' must be one of {sorted(ALLOWED_SOURCES)}: {src!r}"
                )
        if "icd10" in e:
            icd10 = e["icd10"]
            if not isinstance(icd10, str) or not icd10.strip() or not _ICD10_RE.match(icd10):
                raise TermValidationError(
                    f"{loc}: field 'icd10' must be a code like 'E11.9': {icd10!r}"
                )
        if "variants" in e:
            variants = e["variants"]
            if not isinstance(variants, list) or not variants:
                raise TermValidationError(f"{loc}: field 'variants' must be a non-empty list")
            for v in variants:
                if not isinstance(v, str) or not v.strip() or v != v.strip():
                    raise TermValidationError(f"{loc}: variant must be a non-empty string: {v!r}")
                if not _PERSIAN_CHAR.search(v):
                    raise TermValidationError(f"{loc}: variant has no Persian characters: {v!r}")

        key = (fa.casefold(), en.casefold())
        if key in seen_pairs:
            raise TermValidationError(f"{loc}: duplicate entry {fa!r} -> {en!r}")
        seen_pairs.add(key)
        fa_counts[fa] = fa_counts.get(fa, 0) + 1
        en_counts[en.casefold()] = en_counts.get(en.casefold(), 0) + 1

    # Filler-loop heuristic: the same Persian term or the same English term
    # appearing 4+ times means the list was padded with repeated entries.
    for term, n in fa_counts.items():
        if n >= 4:
            raise TermValidationError(f"filler loop suspected: Persian term {term!r} appears {n}x")
    for term, n in en_counts.items():
        if n >= 4:
            raise TermValidationError(f"filler loop suspected: English term {term!r} appears {n}x")

    return entries


def check_all_categories(entries: list[dict]) -> None:
    """Every expected category must be present (a missing file is a bug)."""
    present = {e["cat"] for e in entries}
    missing = REQUIRED_CATEGORIES - present
    if missing:
        raise TermValidationError(f"missing categories: {sorted(missing)}")


def validate_all(terms_dir: Path | None = None) -> list[dict]:
    """Full validation: load every file, check entries and category coverage."""
    entries = load_raw_terms(terms_dir)
    validate_terms(entries)
    check_all_categories(entries)
    return entries
