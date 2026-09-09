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
            assert set(entry) == {"fa", "en", "cat"}, (
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
