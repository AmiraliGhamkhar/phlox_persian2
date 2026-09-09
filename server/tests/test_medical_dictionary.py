"""Quality tests for the bundled Persian-English medical terminology data.

The term lists in ``server/data/terms/*.json`` feed the clinical surfaces
(ASR biasing, the workspace dictionary lookup, the report terminology
reference). These tests fail loudly on structural corruption, junk entries,
or filler loops so a bad dictionary can never ship silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.data.validate_terms import (
    REQUIRED_CATEGORIES,
    TermValidationError,
    check_all_categories,
    load_raw_terms,
    validate_all,
    validate_terms,
)

TERMS_DIR = Path(__file__).resolve().parents[1] / "data" / "terms"


def test_terms_dir_has_files():
    files = sorted(TERMS_DIR.glob("*.json"))
    assert files, "no term files found in server/data/terms"


def test_every_file_is_a_valid_json_array():
    for path in sorted(TERMS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list), f"{path.name} must be a JSON array"
        assert data, f"{path.name} is empty"
        for i, entry in enumerate(data):
            assert isinstance(entry, dict), f"{path.name}[{i}] entry is not an object"
            allowed = {"fa", "en", "cat"}
            optional = {"src", "icd10", "variants"}
            keys = set(entry)
            assert allowed <= keys and keys <= allowed | optional, (
                f"{path.name}[{i}] has extra/missing keys: {entry}"
            )


def test_full_validation_passes():
    entries = validate_all()
    assert len(entries) >= 1000, f"dictionary unexpectedly small: {len(entries)}"


def test_all_categories_present_and_populated():
    entries = validate_all()
    check_all_categories(entries)
    from collections import Counter

    counts = Counter(e["cat"] for e in entries)
    for cat in REQUIRED_CATEGORIES:
        assert counts[cat] >= 5, f"category {cat!r} has only {counts[cat]} entries"


def test_entry_shape_rules():
    """Persian field must contain Persian script; English must be Latin."""
    validate_terms(load_raw_terms())  # raises on any violation


def test_no_duplicate_pairs():
    entries = load_raw_terms()
    seen: set[tuple[str, str]] = set()
    for e in entries:
        key = (e["fa"].casefold(), e["en"].casefold())
        assert key not in seen, f"duplicate {key} in {e.get('_file')}"
        seen.add(key)


def test_duplicate_pair_rejected():
    bad = [
        {"fa": "تب", "en": "fever", "cat": "symptoms"},
        {"fa": "تب", "en": "fever", "cat": "symptoms"},
    ]
    with pytest.raises(TermValidationError, match="duplicate"):
        validate_terms(bad)


def test_persian_without_script_rejected():
    bad = [{"fa": "fever only", "en": "fever", "cat": "symptoms"}]
    with pytest.raises(TermValidationError, match="no Persian"):
        validate_terms(bad)


def test_latin_run_inside_persian_rejected():
    bad = [{"fa": "اسکab", "en": "scabies", "cat": "symptoms"}]
    with pytest.raises(TermValidationError, match="Latin"):
        validate_terms(bad)


def test_persian_inside_english_rejected():
    bad = [{"fa": "تب", "en": "fever و تب", "cat": "symptoms"}]
    with pytest.raises(TermValidationError, match="Persian"):
        validate_terms(bad)


def test_whitespace_normalization_rejected():
    bad = [{"fa": " تب ", "en": "fever", "cat": "symptoms"}]
    with pytest.raises(TermValidationError, match="whitespace"):
        validate_terms(bad)


def test_missing_category_rejected():
    # An entries list missing a whole category should fail the coverage check.
    entries = load_raw_terms()
    trimmed = [e for e in entries if e["cat"] != "obstetric"]
    with pytest.raises(TermValidationError, match="missing categories"):
        check_all_categories(trimmed)


# ------------------------------------------------------- W2.4: provenance


def test_provenance_backfilled():
    """generated/expanded entries are marked generated, everything else curated."""
    entries = load_raw_terms()
    sources = {e["_file"]: e.get("src") for e in entries}
    assert sources["generated.json"] == "generated"
    assert sources["expanded.json"] == "generated"
    for file, src in sources.items():
        if file not in {"generated.json", "expanded.json"}:
            assert src == "curated", file


def test_loader_exposes_provenance():
    from server.data.medical_dictionary import load_terms

    _fa, _en, entries = load_terms()
    assert entries
    assert all(e.get("src") in {"curated", "generated"} for e in entries)


def test_loader_tolerates_entries_without_provenance(tmp_path):
    """Backward compatibility: JSON without src/icd10/variants still loads."""
    import json

    from server.data.medical_dictionary import load_terms

    legacy = [{"fa": "تب شدید آزمون", "en": "test fever probe", "cat": "symptoms"}]
    (tmp_path / "legacy.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    load_terms.cache_clear()
    try:
        import server.data.medical_dictionary as md

        original_dir = md.TERMS_DIR
        md.TERMS_DIR = tmp_path
        load_terms.cache_clear()
        _fa, _en, entries = load_terms()
        assert entries == [{"fa": "تب شدید آزمون", "en": "test fever probe", "cat": "symptoms"}]
    finally:
        md.TERMS_DIR = original_dir
        load_terms.cache_clear()


def test_short_term_does_not_match_inside_longer_word():
    """W2.4 regression: whole-word matching for short terms."""
    from server.data.medical_dictionary import terms_for_context

    # «تب» (fever) is 2 chars; it must not match inside «کتاب».
    inside = terms_for_context("بیمار کتاب می‌خواند")
    assert not any(m["fa"] == "تب" for m in inside)
    whole = terms_for_context("بیمار تب دارد")
    assert any(m["fa"] == "تب" for m in whole)


def test_short_latin_term_whole_word_only():
    from server.data.medical_dictionary import terms_for_context

    # «سرطان پستان» style containment must not fire on substrings of
    # longer Latin words; exact-word hits still count.
    matches = terms_for_context("patient is hopeful about prognosis")
    assert not any(m["en"].casefold() == "pe" for m in matches)


def test_zwnj_variant_matches():
    from server.data.medical_dictionary import terms_for_context

    # بی‌کربنات carries a ZWNJ; matching must ignore it.
    matches = terms_for_context("سطح بیکربنات خون پایین است")
    assert any("بی‌کربنات" in m["fa"] or "بیکربنات" in m["fa"] for m in matches)


def test_terminology_sort_prefers_curated():
    from server.data.medical_dictionary import terms_for_context

    text = "سطح بحرانی بی‌کربنات و تب دارد"
    matches = terms_for_context(text)
    fas = [m["fa"] for m in matches]
    assert "تب" in fas
    # تب is curated (symptoms); سطح بحرانی بی‌کربنات is generated (labs) and
    # much longer — provenance must still win the ordering.
    assert fas.index("تب") < fas.index("سطح بحرانی بی‌کربنات")
    curated_first = matches[fas.index("تب")]
    assert curated_first.get("src") == "curated"


def test_validate_terms_src_enum():
    bad = [{"fa": "تب", "en": "fever", "cat": "symptoms", "src": "wikipedia"}]
    with pytest.raises(TermValidationError, match="src"):
        validate_terms(bad)


def test_validate_terms_variants_shape():
    bad = [{"fa": "تب", "en": "fever", "cat": "symptoms", "variants": ["  "]}]
    with pytest.raises(TermValidationError, match="variant"):
        validate_terms(bad)
    bad2 = [{"fa": "تب", "en": "fever", "cat": "symptoms", "variants": ["tab"]}]
    with pytest.raises(TermValidationError, match="variant"):
        validate_terms(bad2)
    good = [
        {
            "fa": "تب",
            "en": "fever",
            "cat": "symptoms",
            "src": "curated",
            "variants": ["تب بالا"],
        }
    ]
    assert validate_terms(good)


def test_validate_terms_icd10_shape():
    bad = [{"fa": "دیابت نوع ۲", "en": "type 2 diabetes", "cat": "conditions", "icd10": "bogus!"}]
    with pytest.raises(TermValidationError, match="icd10"):
        validate_terms(bad)
