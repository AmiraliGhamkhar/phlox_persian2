"""W1.4/W1.5 guardrail tests for the report system prompt.

* The abstention rule: garbled/uncertain spans must be quoted verbatim or
  omitted — never guessed or corrected.
* The low-confidence block: ASR-flagged spans are injected into the system
  prompt with a "do not treat as established fact" instruction, bounded to
  8 spans of 160 chars each.
"""

from server.nlp_tools.report import (
    REPORT_SYSTEM_PROMPT,
    _low_confidence_block,
    build_report_system_prompt,
)


def test_system_prompt_contains_abstention_rule():
    # Ambiguous/garbled spans: quote verbatim, mark «نامشخص», or omit —
    # never guess, correct, or complete uncertain numbers/doses/findings.
    assert "نامشخص" in REPORT_SYSTEM_PROMPT
    assert "حدس نزن" in REPORT_SYSTEM_PROMPT
    assert "عیناً" in REPORT_SYSTEM_PROMPT
    assert "اصلاح نکن" in REPORT_SYSTEM_PROMPT


def test_system_prompt_keeps_core_safety_rules():
    for phrase in (
        "واقعیت، دارو، دوز، آزمایش یا برنامه اختراع نکن",
        "نفی و تردید را حفظ کن",
        "اعداد، واحدها، نام داروها، مخفف‌ها و شناسه‌ها را دقیقاً حفظ کن",
    ):
        assert phrase in REPORT_SYSTEM_PROMPT


def test_low_confidence_block_empty_without_spans():
    assert _low_confidence_block(None) == ""
    assert _low_confidence_block([]) == ""
    assert _low_confidence_block(["", "  "]) == ""


def test_low_confidence_block_lists_spans_with_instruction():
    block = _low_confidence_block(["فشار خون صد و سی", "HbA1c 7.2"])
    assert "فشار خون صد و سی" in block
    assert "HbA1c 7.2" in block
    assert "نامطمئن" in block
    assert "عیناً" in block
    assert "نامشخص" in block


def test_low_confidence_block_caps_spans_and_length():
    spans = [f"سپان {i}" * 10 for i in range(20)]
    block = _low_confidence_block(spans)
    # At most 8 spans in the block.
    assert block.count("- «") == 8
    # Each span truncated to 160 chars.
    for line in block.splitlines():
        if line.startswith("- «"):
            assert len(line) <= 1 + 1 + 160 + 1  # "- «" + 160 + "»"


def test_low_confidence_block_deduplicates():
    block = _low_confidence_block(["همان عبارت", "همان عبارت", "عبارت دوم"])
    assert block.count("همان عبارت") == 1


def test_build_report_system_prompt_injects_spans():
    prompt = build_report_system_prompt(
        specialty="Cardiology",
        mode="dictate",
        transcript="بیمار با درد قفسه سینه مراجعه کرد",
        low_confidence_spans=["فشار خون صد و سی"],
    )
    assert "فشار خون صد و سی" in prompt
    assert "نامطمئن" in prompt


def test_build_report_system_prompt_without_spans_has_no_block():
    prompt = build_report_system_prompt(
        specialty="Cardiology",
        mode="dictate",
        transcript="بیمار با درد قفسه سینه مراجعه کرد",
    )
    assert "قطعات کم‌اعتمادی" not in prompt
