"""Phase 4 tests — benchmark gate, save-time audit, stats endpoint, CI wiring.

Covers plan refs C1 (harness + fixtures), C2 (nightly gate), C3 (stats +
save-time comparison). The offline gate is the contract: every planted
failure mode must be caught by the shipped guards, in a plain stdlib-only
environment (this doubles as the regression test for the guards themselves).
"""

import json
from pathlib import Path

from server.bench import load_fixtures
from server.bench.run_bench import run_offline


class TestOfflineBenchGate:
    def test_every_plant_is_caught_and_gold_is_clean(self):
        summary = run_offline()
        assert summary["missed"] == [], f"guards missed planted failures: {summary['missed']}"
        assert summary["gold_problems"] == []
        assert summary["plants"] >= 20
        assert summary["caught"] == summary["plants"]

    def test_fixtures_cover_both_languages_and_kinds(self):
        fixtures = load_fixtures()
        langs = {f.lang for f in fixtures}
        assert {"fa", "en"} <= langs
        kinds = {m.kind for f in fixtures for m in f.mutations}
        assert {"fabrication", "number_drift", "negation_flip", "artifact"} == kinds

    def test_fixture_ids_unique(self):
        ids = [f.id for f in load_fixtures()]
        assert len(ids) == len(set(ids))


class TestGenerationReports:
    def _isolate(self, monkeypatch, tmp_path):
        from server.utils import generation_reports as gr

        monkeypatch.setattr(gr, "_report_dir", lambda: tmp_path)
        return gr

    def test_save_audit_compares_against_generation_report(self, monkeypatch, tmp_path):
        gr = self._isolate(monkeypatch, tmp_path)
        transcript = "بیمار از درد شکم شکایت دارد و دوز ۴۰ میلی گرم داده شد"
        gr.record_generation(
            note_id=5,
            template_key="soap",
            transcript=transcript,
            fields={"meds": "• دوز ۸۰ میلی گرم"},
            verification={"mode": "flag", "numberProblems": [{"field": "meds", "value": "80"}]},
        )
        # Clinician fixed the dose to what the transcript supports before saving
        path = gr.record_save(
            note_id=5,
            template_key="soap",
            transcript=transcript,
            fields={"meds": "• دوز ۴۰ میلی گرم"},
        )
        assert path is not None
        saved = path.read_text(encoding="utf-8")
        assert "resolved_at_save" in saved
        data = json.loads(saved)
        assert data["resolved_at_save"] == 1
        assert data["persisting_at_save"] == 0
        stats = gr.stats()
        assert stats["saves"]["count"] == 1
        assert stats["saves"]["resolved"] == 1
        assert stats["reports"] == 1  # save rows excluded from generation count

    def test_save_audit_persisting_when_untouched(self, monkeypatch, tmp_path):
        gr = self._isolate(monkeypatch, tmp_path)
        transcript = "درد شکم گزارش شد"
        gr.record_generation(
            note_id=6,
            template_key="soap",
            transcript=transcript,
            fields={"hpi": "• بیمار سابقه پیوند دارد"},
            verification={
                "mode": "flag",
                "unsupportedQuotes": [
                    {"field": "hpi", "point": "بیمار سابقه پیوند دارد", "score": 0.1}
                ],
            },
        )
        saved_path = gr.record_save(
            note_id=6,
            template_key="soap",
            transcript=transcript,
            fields={"hpi": "• بیمار سابقه پیوند دارد"},
        )
        data = json.loads(saved_path.read_text(encoding="utf-8"))
        assert data["persisting_at_save"] == 1
        assert data["resolved_at_save"] == 0

    def test_record_save_fail_open(self, monkeypatch, tmp_path):
        gr = self._isolate(monkeypatch, tmp_path)
        import server.transcription.verification as v

        def boom(*args, **kwargs):
            del args, kwargs
            raise RuntimeError("nope")

        monkeypatch.setattr(v, "verify_note", boom)
        assert gr.record_save(note_id=1, template_key=None, transcript="t", fields={}) is None


class TestAuditEndpoint:
    def test_route_registered(self):
        from server.api.audit import router

        assert any("/generation-stats" in getattr(r, "path", "") for r in router.routes)

    def test_handler_reads_stats(self, monkeypatch, tmp_path):
        import server.api.audit as audit_api
        from server.utils import generation_reports as gr

        monkeypatch.setattr(gr, "_report_dir", lambda: tmp_path)
        gr.record_generation(
            note_id=9,
            template_key=None,
            transcript="t",
            fields={},
            verification={"numberProblems": [{"field": "a", "value": "1"}]},
        )
        payload = audit_api.generation_stats(limit=50)
        assert payload["reports"] == 1
        assert payload["flagged"] == 1
        assert payload["counters"]["flags:numberProblems"] == 1


class TestNightlyWiring:
    def test_workflow_runs_offline_gate(self):
        import pytest

        wf = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "nightly.yml"
        if not wf.exists():
            # the CI test image ships only server/; the workflow file is
            # exercised by the real Actions run itself
            pytest.skip("workflow file not present in this environment")
        text = wf.read_text(encoding="utf-8")
        assert "precision_gate" in text
        assert "server.bench.run_bench --mode offline" in text

    def test_bench_package_is_import_light(self):
        # The offline gate must not drag the app stack in: dataset + runner
        # import stdlib + package-local modules only.
        import subprocess
        import sys

        repo = str(Path(__file__).resolve().parents[2])
        code = (
            "import sys, json; "
            f"sys.path.insert(0, {repo!r}); "
            "import server.bench.run_bench as rb; "
            "mods=[m for m in sys.modules if m.startswith('server.')]; "
            "print(json.dumps(sorted(mods)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, result.stderr
        import json as _json

        loaded = _json.loads(result.stdout.strip().splitlines()[-1])
        heavy = [
            m
            for m in loaded
            if m.startswith(("server.database", "server.api", "server.llm_client"))
        ]
        assert heavy == []
