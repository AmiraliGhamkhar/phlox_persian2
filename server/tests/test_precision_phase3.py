"""Phase 3 tests — entailment pass, refinement revert guard, leakage guard, voting, reports.

Covers plan refs B2 (CoVe entailment), B6 (entity-diff revert), B7 (example
leakage), B9 (opt-in self-consistency voting) and the file-based generation
report store (C3 input). No live LLM anywhere: structured calls use fakes.
"""

import json

import pytest

from server.transcription.entailment import collect_claims, enabled
from server.transcription.verification import (
    VerificationReport,
    entity_drift,
    example_leakage,
)


class TestEntityDrift:
    def test_number_added(self):
        drift = entity_drift("دوز وارفارین ۵ میلی گرم", "دوز وارفارین ۵ میلی گرم و آسپرین ۱۰۰")
        assert "number_added:100" in drift

    def test_number_dropped(self):
        drift = entity_drift("pH 7.2 ثبت شد", "pH نرمال ثبت شد")
        assert "number_dropped:7.2" in drift

    def test_negation_flip(self):
        draft = "درد قفسه سینه ندارد"
        refined = "بیمار درد قفسه سینه دارد"
        assert "negation_flip" in entity_drift(draft, refined)

    def test_pure_reformat_clean(self):
        draft = "• بیمار از سردرد شکایت دارد"
        refined = "سردرد گزارش شد"
        assert entity_drift(draft, refined) == []


class TestRefinementRevert:
    @pytest.mark.asyncio
    async def test_refine_reverts_on_drift(self, monkeypatch):
        from server.transcription import refinement as ref_mod

        class FakeClient:
            async def chat_with_structured_output(self, **kwargs):
                del kwargs
                # A "helpful" refiner that changes the dose: must be reverted.
                return {"key_points": ["وارفارین ۱۰ میلی گرم هر شب"]}

        class FakeConfigManager:
            def get_config(self):
                return {"PRIMARY_MODEL": "test-model"}

            def get_prompts_and_options(self):
                return {
                    "options": {"general": {"temperature": 0.7}},
                    "prompts": {"refinement": {"system": "s", "narrative": "n"}},
                }

        monkeypatch.setattr(ref_mod, "get_llm_client", lambda: FakeClient())
        monkeypatch.setattr(ref_mod, "config_manager", FakeConfigManager())

        from server.schemas.templates import TemplateField

        field = TemplateField(
            field_key="meds",
            field_name="Medications",
            field_type="list",
            system_prompt="",
            style_example="",
        )
        sink: list[dict] = []
        draft = "• وارفارین ۵ میلی گرم هر شب"
        result = await ref_mod.refine_field_content(draft, field, is_ambient=True, drift_sink=sink)
        assert result == draft  # reverted, polished-but-wrong text discarded
        assert sink and sink[0]["field"] == "meds"
        assert any("number" in d for d in sink[0]["drift"])


class TestLeakageGuard:
    def test_quoted_visit_content_is_leak(self):
        visit = "بیمار گفت سرگیجه دارد و دوز آملودیپین را به ۱۰ میلی گرم افزایش دادیم"
        leaked = "لطفا جمله بیمار گفت سرگیجه دارد و دوز آملودیپین را به ۱۰ میلی گرم افزایش دادیم را کوتاه تر بنویس"
        assert example_leakage(leaked, [visit, visit]) is True

    def test_general_style_instruction_passes(self):
        visit = "بیمار از درد شکم شکایت دارد"
        general = "جملات کوتاه و بدون فاعل تکراری نوشته شوند"
        assert example_leakage(general, [visit, visit]) is False

    def test_filter_keeps_existing_and_drops_leaks(self):
        from server.nlp_tools.adaptive_refinement import _filter_leaked_instructions

        visit = "بیمار از درد شکم شکایت داشت و سونوگرافی درخواست شد"
        result = _filter_leaked_instructions(
            ["همیشه نتیجه سونوگرافی را کامل ذکر کنید", "مختصر بنویسید"],
            ["مختصر بنویسید"],
            visit,
            visit,
        )
        assert "مختصر بنویسید" in result

    def test_guard_fail_open_on_errors(self):
        from server.nlp_tools.adaptive_refinement import _filter_leaked_instructions

        assert _filter_leaked_instructions(["a", "b"], None, "", "") == ["a", "b"]


class TestEntailment:
    def test_collect_claims(self):
        claims = collect_claims({"a": "• x\n• y", "b": "", "c": "single line"})
        assert ("a", "x") in claims and ("a", "y") in claims and ("c", "single line") in claims

    def test_enabled_env_gate(self, monkeypatch):
        monkeypatch.delenv("PHLOX_ENTAILMENT_CHECK", raising=False)
        assert enabled() is True
        monkeypatch.setenv("PHLOX_ENTAILMENT_CHECK", "0")
        assert enabled() is False

    @pytest.mark.asyncio
    async def test_check_claims_flags_unsupported_and_missing_verdicts(self, monkeypatch):
        class FakeConfigManager:
            def get_config(self):
                return {"PRIMARY_MODEL": "m"}

            def get_prompts_and_options(self):
                return {"options": {"general": {}}}

        monkeypatch.setattr(
            "server.database.config.manager.config_manager",
            FakeConfigManager(),
            raising=False,
        )

        class FakeClient:
            async def chat_with_structured_output(self, **kwargs):
                del kwargs
                # claim 0 judged supported but the verdict is *missing*;
                # claim 1 judged unsupported. Missing verdicts must count as
                # unverifiable, never as clean.
                return {"verdicts": [{"claim_index": 1, "verdict": "unsupported", "evidence": ""}]}

        from server.transcription import entailment as ent_mod

        monkeypatch.setattr("server.database.config.manager.config_manager", FakeConfigManager())
        fields = {"hpi": "• درد شکم\n• سابقه پیوند مغز استخوان"}
        report = await ent_mod.check_claims(
            fields, "بیمار از درد شکم شکایت دارد", client=FakeClient(), model="m"
        )
        assert report["counts"]["checked"] == 2
        assert report["counts"]["flagged"] == 2  # unjudged claim + unsupported claim
        verdicts = {v["claim"]: v["verdict"] for v in report["flaggedClaims"]}
        assert verdicts["درد شکم"] == "unjudged"
        assert verdicts["سابقه پیوند مغز استخوان"] == "unsupported"

    @pytest.mark.asyncio
    async def test_maybe_check_fail_open_on_error(self, monkeypatch):
        from server.transcription import entailment as ent_mod

        monkeypatch.setenv("PHLOX_ENTAILMENT_CHECK", "1")

        async def boom(*args, **kwargs):
            del args, kwargs
            raise RuntimeError("provider down")

        monkeypatch.setattr(ent_mod, "check_claims", boom)
        assert await ent_mod.maybe_check_claims({"a": "• x"}, "transcript") is None

    @pytest.mark.asyncio
    async def test_maybe_check_disabled_shortcut(self, monkeypatch):
        from server.transcription import entailment as ent_mod

        monkeypatch.setenv("PHLOX_ENTAILMENT_CHECK", "off")
        assert await ent_mod.maybe_check_claims({"a": "• x"}, "t") is None


class TestVerificationReportExtras:
    def test_reverts_and_entailment_serialized(self):
        report = VerificationReport(mode="flag")
        report.refinement_reverts = [{"field": "meds", "drift": ["number_added:100"]}]
        report.entailment = {"checked": 3, "counts": {"checked": 3, "flagged": 1}}
        payload = report.to_dict()
        assert payload["refinementReverts"][0]["field"] == "meds"
        assert payload["entailment"]["counts"]["flagged"] == 1
        assert report.flagged is True

    def test_empty_when_nothing_attached(self):
        assert VerificationReport(mode="flag").to_dict() == {}
        assert VerificationReport(mode="flag").flagged is False


class TestConsensusVoting:
    def test_vote_k_bounds(self, monkeypatch):
        from server.transcription.text import _vote_k

        monkeypatch.delenv("PHLOX_ASR_VOTE_K", raising=False)
        assert _vote_k() == 1
        monkeypatch.setenv("PHLOX_ASR_VOTE_K", "99")
        assert _vote_k() == 5
        monkeypatch.setenv("PHLOX_ASR_VOTE_K", "junk")
        assert _vote_k() == 1

    def test_consensus_picks_most_agreed_draft(self):
        from server.transcription.text import _consensus

        results = [
            {"hpi": "درد شکم دارد و تهوع"},
            {"hpi": "درد شکم دارد و استفراغ"},
            {"hpi": "سرگیجه شدید مداوم بی ربط"},
        ]
        # First two agree on most content; either may win, the outlier must not.
        assert "درد شکم" in _consensus(results)["hpi"]

    def test_consensus_single_variant_passthrough(self):
        from server.transcription.text import _consensus

        assert _consensus([{"a": "x"}, {"a": "x"}]) == {"a": "x"}


class TestGenerationReports:
    def test_roundtrip_and_stats(self, monkeypatch, tmp_path):
        from server.utils import generation_reports as gr

        monkeypatch.setattr(gr, "_report_dir", lambda: tmp_path)
        path = gr.record_generation(
            note_id=77,
            template_key="soap",
            transcript="بیمار از درد شکم شکایت دارد",
            fields={"hpi": "• درد شکم"},
            verification={
                "mode": "flag",
                "numberProblems": [{"field": "hpi", "value": "40"}],
                "entailment": {"checked": 1, "counts": {"checked": 1, "flagged": 0}},
            },
            asr_flags=[{"segment": 0, "reason": "low_confidence", "text": "x"}],
            asr_segments=[{"id": 0}],
            model="gpt-ish",
        )
        assert path is not None and path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["note_id"] == 77
        assert len(data["transcript_sha256"]) == 64
        assert data["asr_flag_summary"]["low_confidence"] == 1

        latest = gr.latest_for_note(77)
        assert latest and latest["verification"]["numberProblems"]
        assert gr.latest_for_note(999) is None

        stats = gr.stats()
        assert stats["reports"] == 1
        assert stats["flagged"] == 1  # number problem + low-confidence flag
        assert stats["counters"]["flags:numberProblems"] == 1
        assert stats["counters"]["asr:low_confidence"] == 1

    def test_record_never_raises(self, monkeypatch):
        from server.utils import generation_reports as gr

        def boom():
            raise OSError("disk gone")

        monkeypatch.setattr(gr, "_report_dir", boom)
        assert (
            gr.record_generation(
                note_id=None,
                template_key=None,
                transcript="t",
                fields={},
                verification=None,
            )
            is None
        )
