"""Phase 5 tests — ASR comparison scorer (plan ref A7).

Covers the metric functions and the CLI of scripts/bench_asr_models.py:
WER/CER/MER behavior on Persian folding, entity miss counting, fixture
mode and gate exits.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "bench_asr_models.py"


def _load_scorer():
    spec = importlib.util.spec_from_file_location("bench_asr_models", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S = _load_scorer()


class TestMetrics:
    def test_perfect_match_zero(self):
        r = S.normalize_for_match("بیمار درد شکم دارد")
        score = S.score_pair("بیمار، درد شکم دارد!", r)
        assert score["wer"] == 0.0 and score["cer"] == 0.0 and score["mer"] == 0.0

    def test_one_word_substitution(self):
        ref = S.normalize_for_match("the patient has chest pain")
        hyp = S.normalize_for_match("the patient has back pain")
        assert S.wer(ref, hyp) == 1 / 5

    def test_persian_digit_folding_not_an_error(self):
        ref = "دوز ۴۰ میلی گرم"
        hyp = "دوز 40 میلی\u200cگرم"
        score = S.score_pair(ref, hyp)
        assert score["wer"] == 0.0
        assert score["mer"] == 0.0

    def test_mer_detects_missed_dose_and_extra_fact(self):
        ref = S.normalize_for_match("omeprazole 40 mg nightly lisinopril 10 mg")
        hyp = S.normalize_for_match("omeprazole 20 mg nightly")
        rate, detail = S.mer(ref, hyp)
        assert rate > 0.0
        assert "num:40" in detail["missed"]
        assert "tok:lisinopril" in detail["missed"]
        assert "num:20" in detail["hallucinated_entities"]

    def test_empty_reference(self):
        assert S.wer("", "x") == 1.0
        assert S.wer("", "") == 0.0


class TestCli:
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120
        )

    def test_dirs_mode_and_json(self, tmp_path):
        refs = tmp_path / "refs"
        hyp = tmp_path / "hyp_x"
        refs.mkdir()
        hyp.mkdir()
        (refs / "a.txt").write_text(
            "بیمار درد شکم دارد و ۴۰ میلی گرم مصرف می کند", encoding="utf-8"
        )
        (refs / "b.txt").write_text("patient takes omeprazole 40 mg nightly", encoding="utf-8")
        (hyp / "a.txt").write_text("بیمار درد شکم دارد و ۸۰ میلی گرم مصرف می کند", encoding="utf-8")
        (hyp / "b.txt").write_text("patient takes omeprazole 40 mg nightly", encoding="utf-8")
        out = tmp_path / "report.json"
        result = self._run("--refs", str(refs), "--hyp", str(hyp), "--json", str(out))
        assert result.returncode == 0, result.stderr
        report = json.loads(out.read_text(encoding="utf-8"))
        agg = report["hyp_x"]["aggregate"]
        assert agg["files"] == 2
        assert agg["wer"] > 0  # the 40→80 digit change hurts WER…
        assert report["hyp_x"]["per_file"]["b"]["wer"] == 0.0
        # …and the missed entity is listed
        assert "num:80" in report["hyp_x"]["per_file"]["a"]["hallucinated_entities"]
        assert "num:40" in report["hyp_x"]["per_file"]["a"]["missed"]

    def test_gate_mode_fails_on_high_wer(self, tmp_path):
        refs = tmp_path / "refs"
        hyp = tmp_path / "hyp_bad"
        refs.mkdir()
        hyp.mkdir()
        (refs / "a.txt").write_text("الف ب ج د ه و ز ح", encoding="utf-8")
        (hyp / "a.txt").write_text("ت ث ج خ د ذ ر ز س ش", encoding="utf-8")
        result = self._run("--refs", str(refs), "--hyp", str(hyp), "--max-wer", "0.1")
        assert result.returncode == 1

    def test_from_fixtures_missing_hypothesis_errors(self, tmp_path):
        empty = tmp_path / "nothing"
        empty.mkdir()
        fixtures = REPO / "server" / "bench" / "fixtures" / "precision_fa_en.jsonl"
        result = self._run("--from-fixtures", str(fixtures), "--hyp", str(empty))
        assert result.returncode == 1
        assert "missing hypothesis" in result.stderr
