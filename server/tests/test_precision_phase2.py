"""Phase 2 verification tests — quote validation, numeric/negation trace, strictness.

Covers docs/phlox-accuracy-hallucination-plan.md refs B1, A6, A5 (response
plumbing), B5 and B8. All deterministic: no LLM, no network.
"""

import json
from types import SimpleNamespace

import pytest

from server.schemas.grammars import MultiFieldResponse, ProposedJob
from server.transcription.verification import (
    VerificationReport,
    _build_trigrams,
    extract_numbers,
    join_bullets,
    negation_conflicts,
    normalize_for_match,
    number_mismatches,
    quote_support,
    split_bullets,
    verify_draft,
    verify_final_fields,
)


class TestNormalization:
    def test_persian_digits_and_zwnj_fold(self):
        a = normalize_for_match("۴۰ میلی‌گرم")
        b = normalize_for_match("40 میلی\u200cگرم")
        assert a == b

    def test_arabic_yeh_kefold(self):
        assert normalize_for_match("يك") == normalize_for_match("یک")

    def test_punctuation_case_insensitive(
        self,
    ):
        assert normalize_for_match("Chest Pain!") == "chest pain"


class TestNumbers:
    def test_persian_digits_and_units(self):
        facts = extract_numbers("۴۰ میلی گرم روزانه")
        assert facts and facts[0]["value"] == "40"
        assert facts[0]["unit"] and "میلی" in facts[0]["unit"]

    def test_decimal_and_thousands_canonical(self):
        values = {f["value"] for f in extract_numbers("HbA1c 7.20, weight 1,200 g")}
        assert "7.2" in values
        assert "1200" in values

    def test_mismatch_detection(self):
        transcript_norm = normalize_for_match("۴۰ میلی گرم داده شد")
        facts = {f["value"] for f in extract_numbers("۴۰ میلی گرم داده شد")}
        assert number_mismatches("دوز ۸۰ میلی‌گرم", facts, transcript_norm) == ["80"]
        assert number_mismatches("دوز ۴۰ میلی‌گرم", facts, transcript_norm) == []

    def test_no_numbers_no_problems(self):
        assert number_mismatches("بدون تغییر دارو", set(), "") == []


class TestNegations:
    def test_flags_flipped_negation(self):
        transcript = "بیمار درد قفسه سینه ندارد. تب دارد."
        conflicts = negation_conflicts(["بیمار درد قفسه سینه دارد"], transcript)
        assert len(conflicts) == 1
        assert "درد" in conflicts[0]["shared_terms"]

    def test_keeps_negation_in_note(self):
        transcript = "بیمار درد قفسه سینه ندارد"
        assert negation_conflicts(["درد قفسه سینه ندارد"], transcript) == []

    def test_english_word_boundary_cues(self):
        # "note"/"protocol" must not count as negations
        assert negation_conflicts(["protocol documented"], "the note lists findings") == []
        flips = negation_conflicts(["patient reports chest pain"], "the patient denies chest pain")
        assert len(flips) == 1


class TestQuoteSupport:
    def test_verbatim_supported(self):
        tr = "بیمار مرد ۵۲ ساله با سابقه دیابت مراجعه کرده و از تشنگی شدید شکایت دارد"
        trn = normalize_for_match(tr)
        tri = _build_trigrams(trn)
        assert quote_support("سابقه دیابت", trn, tri) >= 0.85

    def test_fabricated_fact_flagged(self):
        trn = normalize_for_match("بیمار از سردرد شکایت دارد")
        tri = _build_trigrams(trn)
        score = quote_support("بیمار از سردرد شکایت دارد و آسپرین روزانه تجویز شد", trn, tri)
        assert score < 0.85

    def test_empty_point_is_supported(self):
        assert quote_support("", "anything", set()) == 1.0


class TestDraftVerificationModes:
    def test_flag_mode_keeps_all_and_reports(self):
        fields = {"hpi": ["بیمار از درد شکم شکایت دارد", "بیمار داروهای ضدانعقاد شروع کرده است"]}
        transcript = "بیمار از درد شکم شکایت دارد"
        kept, report = verify_draft(fields, transcript, mode="flag")
        assert kept["hpi"] == fields["hpi"]
        assert report.flagged
        assert report.unsupported[0]["field"] == "hpi"

    def test_strict_mode_drops_unsupported(self):
        fields = {"hpi": ["بیمار از درد شکم شکایت دارد", "بیمار داروهای ضدانعقاد شروع کرده است"]}
        transcript = "بیمار از درد شکم شکایت دارد"
        kept, report = verify_draft(fields, transcript, mode="strict")
        assert kept["hpi"] == ["بیمار از درد شکم شکایت دارد"]
        assert len(report.unsupported) == 1


class TestFinalFieldTrace:
    def test_numbers_and_negations_attach_to_report(self):
        report = VerificationReport(mode="flag")
        fields = {
            "meds": join_bullets(["وارفارین ۵ میلی‌گرم هر شب"]),
        }
        transcript = "وارفارین دو و نیم میلی گرم هر شب"
        out = verify_final_fields(fields, transcript, report)
        assert any(p["field"] == "meds" for p in out.number_problems)

    def test_clean_note_produces_empty_dict(self):
        report = VerificationReport(mode="flag")
        out = verify_final_fields({"hpi": "• درد شکم"}, "بیمار از درد شکم شکایت دارد", report)
        assert out.to_dict() == {}


class TestBulletRoundTrip:
    def test_split_join(self):
        content = "• نکته یک\n• نکته دو"
        assert split_bullets(content) == ["نکته یک", "نکته دو"]
        assert join_bullets(["a", "b"]) == "• a\n• b"


class TestStrictModeGate:
    def test_multi_field_schema_is_strict_compatible(self):
        from server.llm_client.providers.openai import _strict_compatible

        schema = MultiFieldResponse.model_json_schema()
        assert _strict_compatible(schema) is True

    def test_optional_field_schema_not_compatible(self):
        from server.llm_client.providers.openai import _strict_compatible

        schema = ProposedJob.model_json_schema()
        assert _strict_compatible(schema) is False

    @pytest.mark.asyncio
    async def test_openai_provider_sets_strict_for_compatible_schema(self):
        from server.llm_client.providers.openai import openai_compatible_chat

        captured = {}

        async def fake_create(**params):
            captured.update(params)
            msg = SimpleNamespace(
                content="{}", reasoning=None, reasoning_content=None, thinking=None, tool_calls=None
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        schema = MultiFieldResponse.model_json_schema()
        await openai_compatible_chat(client, "m", [{"role": "user", "content": "x"}], format=schema)
        assert captured["response_format"]["json_schema"]["strict"] is True

        # Incompatible schema keeps legacy behaviour (no strict key).
        await openai_compatible_chat(
            client, "m", [{"role": "user", "content": "x"}], format=ProposedJob.model_json_schema()
        )
        assert "strict" not in captured["response_format"]["json_schema"]

    def test_forbid_extras_blocks_unknown_keys(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MultiFieldResponse.model_validate({"field_summaries": {}, "extra_key": 1})
        ok = MultiFieldResponse.model_validate_json(json.dumps({"field_summaries": {"a": ["b"]}}))
        assert ok.field_summaries == {"a": ["b"]}


class TestResponsePlumbing:
    def test_draft_fields_and_verification_optional(self):
        from server.schemas.patient import TranscribeResponse

        resp = TranscribeResponse(
            fields={"a": "x"},
            rawTranscription="t",
            transcriptionDuration=1.0,
            processDuration=2.0,
            draftFields={"a": "• x"},
            verification={"mode": "flag", "unsupportedQuotes": []},
        )
        assert resp.draftFields == {"a": "• x"}
        assert resp.verification["mode"] == "flag"
        plain = TranscribeResponse(
            fields={"a": "x"},
            rawTranscription="t",
            transcriptionDuration=1.0,
            processDuration=2.0,
        )
        assert plain.draftFields is None and plain.verification is None
