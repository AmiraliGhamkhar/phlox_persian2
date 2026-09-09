"""The nightly precision gate must stay importable as a stdlib-only module."""

from server.bench.guards import detect_fabrication, detect_negation_flip, detect_number_drift
from server.bench.run_bench import main


def test_offline_precision_gate_passes():
    assert main(["--mode", "offline"]) == 0


def test_guards_catch_planted_failures():
    assert "8.1" in detect_number_drift("HbA1c 7.2", "HbA1c 8.1")
    assert detect_negation_flip("درد قفسه سینه ندارد", "درد قفسه سینه دارد")
    assert detect_fabrication("سردرد از دیروز", "سابقه سکته مغزی و دیالیز")


def test_guards_accept_faithful_notes():
    source = "بیمار مرد ۵۲ ساله با درد قفسه سینه از دیروز. HbA1c 7.2. درد شکم ندارد."
    note = "شکایت اصلی: درد قفسه سینه از دیروز. HbA1c 7.2. درد شکم ندارد."
    assert detect_number_drift(source, note) == []
    assert detect_negation_flip(source, note) == []
    assert detect_fabrication(source, note) == []
