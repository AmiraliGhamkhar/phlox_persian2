"""Gold-set acceptance tests for note faithfulness verification.

The gold set (``server/tests/gold/note_pairs.jsonl``) contains faithful
transcript→note pairs; a correct model output must never be flagged.
``planted_errors.jsonl`` contains notes with exactly one known error class;
the detectors must catch the specific class.

The same contract runs in CI via ``python3 -m server.bench.score_notes`` on
the stdlib-only nightly runner; this pytest module keeps the contract inside
the regular test suite as well.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.nlp_tools.verification import (
    detect_negation_flip,
    detect_number_drift,
    verify_note,
)

_GOLD = Path(__file__).resolve().parent / "gold" / "note_pairs.jsonl"
_PLANTED = Path(__file__).resolve().parent / "gold" / "planted_errors.jsonl"


def _load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


GOLD_ROWS = _load(_GOLD)
PLANTED_ROWS = _load(_PLANTED)


def test_gold_set_schema_and_size():
    assert len(GOLD_ROWS) >= 30
    ids = [row["id"] for row in GOLD_ROWS]
    assert len(set(ids)) == len(ids), "gold ids must be unique"
    for row in GOLD_ROWS:
        assert row["id"]
        assert len(row["source"]) >= 20
        assert len(row["note"]) >= 20


def test_planted_set_schema_and_size():
    assert len(PLANTED_ROWS) == 10
    ids = [row["id"] for row in PLANTED_ROWS]
    assert len(set(ids)) == len(ids)
    for row in PLANTED_ROWS:
        assert row.get("expect_kind") in {
            "number_drift",
            "unit_mismatch",
            "negation_flip",
            "ungrounded_term",
            "low_overlap_sentence",
        }


def test_gold_pairs_produce_zero_findings():
    failures = []
    for row in GOLD_ROWS:
        findings = verify_note(row["source"], row["note"]).warnings()
        if findings:
            failures.append(f"{row['id']}: {findings}")
    assert not failures, "faithful notes must never be flagged:\n" + "\n".join(failures)


def test_planted_errors_are_caught_with_expected_kind():
    failures = []
    for row in PLANTED_ROWS:
        kinds = {f["kind"] for f in verify_note(row["source"], row["note"]).warnings()}
        if row["expect_kind"] not in kinds:
            failures.append(f"{row['id']}: expected {row['expect_kind']}, got {sorted(kinds)}")
    assert not failures, "\n".join(failures)


def test_acceptance_negation_preservation_not_flagged():
    """User-verbatim acceptance case: negated finding + affirmed different one."""
    source = "بیمار گفت درد قفسه سینه ندارد، اما درد شکم دارد"
    note = "شکایت اصلی: درد شکم دارد"
    assert detect_negation_flip(source, note) == []


def test_acceptance_negation_flip_still_caught():
    source = "بیمار گفت درد قفسه سینه ندارد، اما درد شکم دارد"
    note = "شکایت اصلی: بیمار درد قفسه سینه دارد"
    flips = detect_negation_flip(source, note)
    assert "درد قفسه سینه" in flips


def test_acceptance_faithful_note_unflagged():
    source = "بیمار مرد ۵۲ ساله با درد قفسه سینه از دیروز. HbA1c 7.2. درد شکم ندارد."
    note = "شکایت اصلی: درد قفسه سینه از دیروز. HbA1c 7.2. درد شکم ندارد."
    assert verify_note(source, note).ok


def test_legacy_number_drift_compat():
    assert "8.1" in detect_number_drift("HbA1c 7.2", "HbA1c 8.1")


def test_legacy_negation_flip_compat():
    assert detect_negation_flip("درد قفسه سینه ندارد", "درد قفسه سینه دارد")


@pytest.mark.parametrize("row", GOLD_ROWS, ids=[row["id"] for row in GOLD_ROWS])
def test_gold_pair_row(row):
    assert verify_note(row["source"], row["note"]).ok


@pytest.mark.parametrize("row", PLANTED_ROWS, ids=[row["id"] for row in PLANTED_ROWS])
def test_planted_row(row):
    kinds = {f["kind"] for f in verify_note(row["source"], row["note"]).warnings()}
    assert row["expect_kind"] in kinds
