"""Unit tests for the ASR eval harness pure helpers (plan W2.6).

The transcription side of ``scripts/eval_asr.py`` needs model weights, so
CI only exercises the scoring/comparison helpers, loaded directly from the
script file (no package import required).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_asr.py"


def _load():
    spec = importlib.util.spec_from_file_location("eval_asr", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eval_asr = _load()


class TestCanonicalization:
    def test_latin_and_arabic_digits_become_persian(self):
        fa = [chr(0x06F0 + i) for i in range(10)]
        text = "dose 123 \u0645\u064a\u0644\u064a\u200c\u06af\u0631\u0645 \u0664\u0665\u0666"
        out = eval_asr.canonicalize(text)
        assert fa[1] in out and fa[2] in out and fa[3] in out
        assert fa[4] in out and fa[5] in out and fa[6] in out
        assert not any(c.isdigit() for c in out if c.isascii())

    def test_yk_normalized(self):
        assert eval_asr.canonicalize("\u0643\u064a\u0633\u062a") == "\u06a9\u06cc\u0633\u062a"

    def test_casefold(self):
        assert eval_asr.canonicalize("Aspirin") == "aspirin"

    def test_score_tokens_strip_zwnj_and_punct(self):
        tokens = eval_asr.score_tokens(
            "\u0628\u06cc\u200c\u0645\u0627\u0631\u06cc\u060c \u062f\u0631\u062f (chest pain)!"
        )
        assert "\u0628\u06cc\u0645\u0627\u0631\u06cc" in tokens
        assert "chest" in tokens and "pain" in tokens
        assert "\u200c" not in "".join(tokens)

    def test_empty_text_no_tokens(self):
        assert eval_asr.score_tokens("   ") == []
        assert eval_asr.score_tokens("") == []


class TestWer:
    def test_exact_match(self):
        r = eval_asr.word_error_rate(["a", "b"], ["a", "b"])
        assert r["wer"] == 0.0 and r["substitutions"] == 0

    def test_substitution_deletion_insertion(self):
        # ref: a b c ; hyp: a x c d -> S(b->x), I(d) = 2 errors / 3
        r = eval_asr.word_error_rate(["a", "b", "c"], ["a", "x", "c", "d"])
        assert r["wer"] == pytest.approx(2 / 3)
        assert r["substitutions"] + r["deletions"] + r["insertions"] == 2

    def test_empty_reference(self):
        assert eval_asr.word_error_rate([], [])["wer"] == 0.0
        assert eval_asr.word_error_rate([], ["x"])["wer"] == 1.0

    def test_empty_hypothesis_all_deletions(self):
        r = eval_asr.word_error_rate(["a", "b"], [])
        assert r["wer"] == 1.0 and r["deletions"] == 2


class TestGoldSet:
    def test_pairs_audio_with_reference(self, tmp_path):
        (tmp_path / "one.wav").write_bytes(b"x")
        (tmp_path / "one.txt").write_text("ref", encoding="utf-8")
        (tmp_path / "two.mp3").write_bytes(b"x")  # no .txt -> skipped
        (tmp_path / "notes.md").write_text("not audio", encoding="utf-8")
        items = eval_asr.collect_gold_set(tmp_path)
        assert [i["audio"].name for i in items] == ["one.wav"]

    def test_missing_dir_empty(self, tmp_path):
        assert eval_asr.collect_gold_set(tmp_path / "nope") == []


class TestEngineSpec:
    def test_plain_and_model_forms(self):
        assert eval_asr.parse_engine_spec("local") == ("local", None)
        assert eval_asr.parse_engine_spec("speechmatics") == ("speechmatics", None)
        assert eval_asr.parse_engine_spec("local:whisper-large-v3-turbo") == (
            "local",
            "whisper-large-v3-turbo",
        )

    def test_unknown_engine_rejected(self):
        with pytest.raises(ValueError, match="unknown engine"):
            eval_asr.parse_engine_spec("deepgram")


class TestRegression:
    def _result(self, **overrides):
        base = {
            "wer_micro": 0.10,
            "normalized_wer_micro": 0.08,
            "bert_score_f1": None,
        }
        base.update(overrides)
        return base

    def test_no_regression_within_tolerance(self):
        baseline = {"wer_micro": 0.10, "normalized_wer_micro": 0.08, "bert_score_f1": None}
        result = self._result(wer_micro=0.103)
        assert eval_asr.check_regression(result, baseline, tolerance=0.005) == []

    def test_regression_beyond_tolerance(self):
        baseline = {"wer_micro": 0.10, "normalized_wer_micro": 0.08, "bert_score_f1": None}
        result = self._result(wer_micro=0.12)
        findings = eval_asr.check_regression(result, baseline, tolerance=0.005)
        assert len(findings) == 1 and "WER" in findings[0]

    def test_bert_score_drop_flagged(self):
        baseline = {"wer_micro": 0.10, "normalized_wer_micro": 0.08, "bert_score_f1": 0.90}
        result = self._result(bert_score_f1=0.80)
        findings = eval_asr.check_regression(result, baseline, tolerance=0.005)
        assert any("BERTScore" in f for f in findings)

    def test_null_baseline_skipped(self):
        baseline = {"wer_micro": None, "normalized_wer_micro": None, "bert_score_f1": None}
        assert eval_asr.check_regression(self._result(wer_micro=0.9), baseline, 0.005) == []


def _fake_evaluate(wer: float):
    """Stand-in for evaluate_set that validates its arguments."""

    def fake_eval(items, provider, model, verbose=False):
        assert items
        assert provider in {"local", "speechmatics"}
        assert model is None or isinstance(model, str)
        assert isinstance(verbose, bool)
        return {
            "wer_micro": wer,
            "wer_macro": wer,
            "normalized_wer_micro": wer,
            "normalized_wer_macro": wer,
            "files": [{"file": "c.wav", "wer": wer, "normalized_wer": wer}],
            "_refs": ["ref"],
            "_hyps": ["hyp"],
        }

    return fake_eval


class TestCli:
    def test_no_clips_exit_code(self, tmp_path, capsys):
        rc = eval_asr.main(["--data-dir", str(tmp_path)])
        assert rc == 2
        assert "no gold clips" in capsys.readouterr().err

    def test_template_baseline_no_regression(self, tmp_path, monkeypatch):
        (tmp_path / "c.wav").write_bytes(b"x")
        (tmp_path / "c.txt").write_text("ref", encoding="utf-8")
        baseline = tmp_path / "base.json"
        baseline.write_text(
            json.dumps({"wer_micro": None, "normalized_wer_micro": None, "bert_score_f1": None}),
            encoding="utf-8",
        )
        monkeypatch.setattr(eval_asr, "evaluate_set", _fake_evaluate(0.5))
        rc = eval_asr.main(["--data-dir", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 0

    def test_regression_exits_nonzero(self, tmp_path, monkeypatch):
        (tmp_path / "c.wav").write_bytes(b"x")
        (tmp_path / "c.txt").write_text("ref", encoding="utf-8")
        baseline = tmp_path / "base.json"
        baseline.write_text(
            json.dumps({"wer_micro": 0.1, "normalized_wer_micro": 0.1, "bert_score_f1": None}),
            encoding="utf-8",
        )
        monkeypatch.setattr(eval_asr, "evaluate_set", _fake_evaluate(0.3))
        rc = eval_asr.main(["--data-dir", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_update_baseline_writes_file(self, tmp_path, monkeypatch):
        (tmp_path / "c.wav").write_bytes(b"x")
        (tmp_path / "c.txt").write_text("ref", encoding="utf-8")
        out = tmp_path / "new_baseline.json"
        monkeypatch.setattr(eval_asr, "evaluate_set", _fake_evaluate(0.25))
        rc = eval_asr.main(
            ["--data-dir", str(tmp_path), "--baseline", str(out), "--update-baseline"]
        )
        assert rc == 0
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["wer_micro"] == 0.25
        assert "_refs" not in written  # internals never leak into the baseline

    def test_compare_mode_runs_both_engines(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "c.wav").write_bytes(b"x")
        (tmp_path / "c.txt").write_text("ref", encoding="utf-8")
        calls = []

        def fake_eval(items, provider, model, verbose=False):
            assert items and isinstance(verbose, bool)
            calls.append((provider, model))
            return {
                "wer_micro": 0.2,
                "wer_macro": 0.2,
                "normalized_wer_micro": 0.15,
                "normalized_wer_macro": 0.15,
                "files": [{"file": "c.wav", "wer": 0.2, "normalized_wer": 0.15}],
                "_refs": ["ref"],
                "_hyps": ["hyp"],
            }

        monkeypatch.setattr(eval_asr, "evaluate_set", fake_eval)
        rc = eval_asr.main(["--data-dir", str(tmp_path), "--compare", "local", "speechmatics"])
        assert rc == 0
        assert calls == [("local", None), ("speechmatics", None)]
        assert "macro WER" in capsys.readouterr().out
