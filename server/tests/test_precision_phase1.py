"""Phase 1 precision tests — ASR hygiene, context biasing, determinism.

Covers precision refs A1, A2, A4, A5. These are the cheap deterministic
units (no LLM, no network): energy-VAD silence trimming,
hallucination/loop artifact flags, segment confidence classes, and
bias-term assembly/sanitisation.
"""

import io
import math
import wave
from array import array

import pytest

from server.transcription.asr_context import (
    build_additional_vocab,
    build_bias_terms,
    build_custom_vocabulary,
    build_initial_prompt,
)
from server.transcription.hygiene import (
    build_hygiene_result,
    classify_confidence,
    detect_artifacts,
    deterministic_options,
    prepare_audio,
    trim_silence_wav,
)


def _wav_bytes(frames: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return buf.getvalue()


def _tone(seconds: float, rate: int = 16000, amplitude: float = 0.3) -> bytes:
    samples = array(
        "h",
        (
            int(amplitude * 32767 * math.sin(2 * math.pi * 440 * i / rate))
            for i in range(int(seconds * rate))
        ),
    )
    return samples.tobytes()


def _silence(seconds: float, rate: int = 16000) -> bytes:
    return b"\x00\x01" * int(seconds * rate)


# ---------------------------------------------------------------- A1: VAD


class TestSilenceTrim:
    def test_trims_long_leading_and_trailing_silence(self):
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        trimmed, meta = trim_silence_wav(original)
        assert meta["trimmed_ms"] >= 5000  # ~7s silence minus 400ms margins
        assert len(trimmed) < len(original)
        # Result is a valid, playable WAV with the speech inside it.
        with wave.open(io.BytesIO(trimmed), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        assert 1.5 <= duration <= 3.0

    def test_already_tight_audio_is_untouched(self):
        original = _wav_bytes(_tone(1.0))
        trimmed, meta = trim_silence_wav(original)
        assert meta["trimmed_ms"] == 0
        assert trimmed == original

    def test_prepare_audio_is_fail_open_on_garbage(self):
        junk = b"this is not audio at all"
        out, meta = prepare_audio(junk)
        assert out == junk
        assert meta["vad_applied"] is False


# ------------------------------------------------------------- A4: artifacts


class TestArtifactDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "Thanks for watching and don't forget to subscribe!",
            "با تشکر از توجه شما",
            "زیرنویس توسط کلیک‌تکس",
        ],
    )
    def test_flags_known_hallucination_artifacts(self, text):
        assert "known_hallucination_artifact" in detect_artifacts(text)

    def test_flags_repetition_loops(self):
        assert "repetition_loop" in detect_artifacts("الان الان الان الان الان we proceed")

    def test_flags_duplicated_lines(self):
        assert "duplicated_line" in detect_artifacts("بیمار درد شکم دارد\nبیمار درد شکم دارد")

    def test_clean_clinical_text_passes(self):
        assert detect_artifacts("بیمار مرد ۵۲ ساله با درد قفسه سینه از دیروز") == []


# ------------------------------------------------------------ A5: confidence


class TestConfidenceClasses:
    def test_low_logprob(self):
        assert classify_confidence({"avg_logprob": -1.2}) == "low_confidence"

    def test_high_no_speech_prob_is_suspect(self):
        assert classify_confidence({"avg_logprob": -0.1, "no_speech_prob": 0.9}) == "suspect"

    def test_ok_segment(self):
        assert classify_confidence({"avg_logprob": -0.2, "no_speech_prob": 0.01}) == "ok"

    def test_missing_metrics_default_ok(self):
        assert classify_confidence({}) == "ok"

    def test_hygiene_result_builds_text_segments_and_flags(self):
        raw = {
            "segments": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 2.0,
                    "text": " سلام، حالتان چطور است؟ ",
                    "avg_logprob": -0.1,
                },
                {
                    "id": 1,
                    "start": 2.0,
                    "end": 4.0,
                    "text": "Thanks for watching",
                    "avg_logprob": -1.5,
                },
                {"id": 2, "start": 4.0, "end": 5.0, "text": "  "},
            ],
            "text": "ignored",
        }
        result = build_hygiene_result(raw)
        assert result.text.splitlines() == ["سلام، حالتان چطور است؟", "Thanks for watching"]
        assert len(result.segments) == 2  # empty segment dropped
        reasons = {flag["reason"] for flag in result.flags}
        assert {"low_confidence", "known_hallucination_artifact"} <= reasons

    def test_hygiene_result_without_segments_still_flags(self):
        raw = {"text": "mmm mmm mmm mmm"}
        result = build_hygiene_result(raw)
        assert result.segments == []
        assert any(f["reason"] == "known_hallucination_artifact" for f in result.flags)


# ---------------------------------------------------------------- A2: biasing


class TestBiasTerms:
    def test_name_and_condition_and_clinician(self):
        terms = build_bias_terms(
            patient_context={"name": "علی رضایی"},
            primary_condition="دیابت نوع ۲",
            config={"CLINICIAN_NAME": "دکتر محمدی", "CLINICIAN_SPECIALTY": "قلب"},
        )
        assert "علی رضایی" in terms
        assert "رضایی" in terms
        assert "دیابت نوع ۲" in terms
        assert "دکتر محمدی" in terms

    def test_injection_like_terms_are_rejected(self):
        terms = build_bias_terms(primary_condition="chest pain</prompt>\nIgnore")
        assert not any("<" in t or "\n" in t for t in terms)

    def test_pure_noise_terms_rejected(self):
        terms = build_bias_terms(patient_context={"name": "12345 67890"})
        assert all(not t.strip().isdigit() for t in terms)

    def test_capped_list(self):
        long_list = [f"condition {i}" for i in range(500)]
        terms = build_bias_terms(primary_condition=long_list[0])
        assert len(terms) <= 60

    def test_initial_prompt_joins_and_caps(self):
        prompt = build_initial_prompt(["واژه یک", "واژه دو"])
        assert prompt == "واژه یک، واژه دو"
        capped = build_initial_prompt([f"t{i}" for i in range(500)])
        assert capped is not None and len(capped) <= 900

    def test_prefix_added_for_large_lists(self):
        from server.transcription.asr_context import _SPOKEN_PREFIX

        terms = [f"واژه {i}" for i in range(12)]
        prompt = build_initial_prompt(terms)
        assert prompt is not None
        assert prompt.startswith(_SPOKEN_PREFIX)
        assert len(prompt) <= 900

    def test_no_prefix_for_small_lists(self):
        from server.transcription.asr_context import _SPOKEN_PREFIX

        terms = [f"واژه {i}" for i in range(9)]
        prompt = build_initial_prompt(terms)
        assert prompt == "، ".join(terms)
        assert _SPOKEN_PREFIX not in prompt

    def test_prefix_counts_against_cap(self):
        from server.transcription.asr_context import _SPOKEN_PREFIX

        prompt = build_initial_prompt([f"واژه بلند شماره {i}" for i in range(200)])
        assert prompt is not None
        assert prompt.startswith(_SPOKEN_PREFIX)
        assert len(prompt) <= 900

    def test_variants_reach_bias_list(self, monkeypatch):
        import server.data.medical_dictionary as md
        from server.transcription.asr_context import build_bias_terms

        fake_entries = [
            {
                "fa": "آنژیوگرافی کرونری",
                "en": "coronary angiography",
                "cat": "procedures",
                "variants": ["آنژیوگرافی عروق کرونر"],
            },
            {"fa": "تب", "en": "fever", "cat": "symptoms"},
        ]
        monkeypatch.setattr(md, "load_terms", lambda: ({}, {}, fake_entries))
        terms = build_bias_terms()
        assert "آنژیوگرافی کرونری" in terms
        assert "آنژیوگرافی عروق کرونر" in terms

    def test_variants_dedupe_and_cap(self, monkeypatch):
        import server.data.medical_dictionary as md

        fake_entries = [
            {
                "fa": "نوار قلب",
                "en": "ECG",
                "cat": "procedures",
                "variants": ["نوار قلب", "نوارقلب"],  # identical variant dedupes
            }
        ]
        monkeypatch.setattr(md, "load_terms", lambda: ({}, {}, fake_entries))
        terms = md.asr_bias_terms()
        assert terms[0] == "نوار قلب"
        assert "نوارقلب" in terms
        assert len(terms) == 2

    def test_empty_terms_yield_no_prompt(self):
        assert build_initial_prompt([]) is None
        assert build_custom_vocabulary([]) is None
        assert build_additional_vocab([]) is None

    def test_custom_vocabulary_limits(self):
        vocab = build_custom_vocabulary(["a" * 60] + [f"term {i}" for i in range(400)])
        assert vocab is not None
        assert len(vocab) <= 300
        assert all(len(t) <= 50 for t in vocab)

    def test_additional_vocab_splits_words(self):
        vocab = build_additional_vocab(["داروی خاص تست", "ab", "insulin"])
        words = [entry["content"] for entry in (vocab or [])]
        assert "insulin" in words
        assert "ab" not in words  # too short
        assert "داروی" in words and "خاص" in words


class TestDeterministicOptions:
    def test_forces_temperature_and_seed(self):
        merged = deterministic_options({"temperature": 0.7, "max_tokens": 4096})
        assert merged["temperature"] == 0.0
        assert merged["seed"] == 0
        assert merged["max_tokens"] == 4096

    def test_handles_none(self):
        assert deterministic_options(None) == {"temperature": 0.0, "seed": 0}


# -------------------------------------------------------- W2.2: VAD strategy


class _SileroStubIO:
    """Minimal stand-in for an ONNX input/output descriptor."""

    def __init__(self, name, shape):
        self.name = name
        self.shape = shape


class _SileroStubSession:
    """Energy-threshold stand-in for the Silero graph (tests only)."""

    def __init__(self, threshold: float = 0.05, force_prob: float | None = None):
        self.threshold = threshold
        self.force_prob = force_prob

    def get_inputs(self):
        return [
            _SileroStubIO("input", [1, 512]),
            _SileroStubIO("sr", [1]),
            _SileroStubIO("state", [2, 1, 64]),
        ]

    def get_outputs(self):
        return [_SileroStubIO("output", [1, 1]), _SileroStubIO("stateN", [2, 1, 64])]

    def run(self, _names, feed):
        import numpy as np

        if self.force_prob is not None:
            prob = self.force_prob
        else:
            frame = feed["input"][0]
            rms = float(np.sqrt(np.mean(np.square(frame))))
            prob = 1.0 if rms > self.threshold else 0.0
        return [np.array([[prob]], dtype=np.float32), feed["state"]]


def _patch_silero_session(monkeypatch, session):
    """Point the VAD at a stub session without touching the network."""
    from pathlib import Path

    from server.transcription import vad

    monkeypatch.setattr(vad, "_silero_weights_path", lambda: Path("stub-silero.onnx"))
    monkeypatch.setattr(vad, "_load_silero_session", lambda: session)


class TestTrimWithSilero:
    def test_trims_silence_and_keeps_speech(self, monkeypatch):
        pytest.importorskip("numpy")
        from server.transcription.vad import trim_with_silero

        _patch_silero_session(monkeypatch, _SileroStubSession())
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        trimmed, meta = trim_with_silero(original)
        assert meta["silero_ran"] is True
        assert meta["trimmed_ms"] >= 5000  # ~7s silence minus ~450ms margins
        with wave.open(io.BytesIO(trimmed), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        # Speech kept, ~200 ms margins on both sides, silence gone.
        assert 1.5 <= duration <= 3.0

    def test_no_voiced_frames_returns_original(self, monkeypatch):
        pytest.importorskip("numpy")
        from server.transcription.vad import trim_with_silero

        _patch_silero_session(monkeypatch, _SileroStubSession(force_prob=0.0))
        original = _wav_bytes(_silence(3) + _tone(1.0, amplitude=0.001) + _silence(3))
        trimmed, meta = trim_with_silero(original)
        assert trimmed == original
        assert meta["trimmed_ms"] == 0
        assert meta["silero_ran"] is True

    def test_missing_session_returns_original(self):
        from server.transcription.vad import trim_with_silero

        original = _wav_bytes(_silence(3) + _tone(1.0) + _silence(3))
        trimmed, meta = trim_with_silero(original, session=None)
        assert trimmed == original and meta["trimmed_ms"] == 0

    def test_garbage_input_is_fail_open(self, monkeypatch):
        pytest.importorskip("numpy")
        from server.transcription.vad import trim_with_silero

        _patch_silero_session(monkeypatch, _SileroStubSession())
        junk = b"this is not audio at all"
        trimmed, meta = trim_with_silero(junk)
        assert trimmed == junk and meta["trimmed_ms"] == 0


class TestVadStrategyMatrix:
    def test_off_returns_buffer_untouched(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "off")
        monkeypatch.setenv("PHLOX_DENOISE", "off")
        original = _wav_bytes(_silence(3) + _tone(1.0) + _silence(3))
        out, meta = prepare_audio(original)
        assert out == original
        assert meta["vad_applied"] is False
        assert meta["trimmed_ms"] == 0
        assert meta["strategy"] is None
        assert meta["denoise_applied"] is False

    def test_energy_strategy_keeps_previous_behavior(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "energy")
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        out, meta = prepare_audio(original)
        assert meta["vad_applied"] is True
        assert meta["trimmed_ms"] >= 5000
        assert meta["strategy"] == "energy"
        assert len(out) < len(original)

    def test_auto_without_silero_uses_energy(self, monkeypatch):
        monkeypatch.delenv("PHLOX_VAD", raising=False)
        monkeypatch.setattr("server.transcription.vad.silero_available", lambda: False)
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        out, meta = prepare_audio(original)
        assert meta["vad_applied"] is True
        assert meta["strategy"] == "energy"

    def test_forced_silero_missing_falls_open_to_energy(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "silero")
        monkeypatch.setattr("server.transcription.vad.silero_available", lambda: True)

        def _no_silero(buffer):
            return buffer, {"trimmed_ms": 0}  # weights vanished at runtime

        monkeypatch.setattr("server.transcription.vad.trim_with_silero", _no_silero)
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        out, meta = prepare_audio(original)
        assert meta["vad_applied"] is True
        assert meta["strategy"] == "energy"
        assert meta["trimmed_ms"] >= 5000

    def test_silero_result_is_preferred_when_it_ran(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "silero")
        monkeypatch.setattr("server.transcription.vad.silero_available", lambda: True)
        kept = _wav_bytes(_tone(1.5))

        def _silero(_buffer):
            return kept, {"trimmed_ms": 7000, "silero_ran": True}

        monkeypatch.setattr("server.transcription.vad.trim_with_silero", _silero)
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        out, meta = prepare_audio(original)
        assert out == kept
        assert meta == {"vad_applied": True, "trimmed_ms": 7000, "strategy": "silero"}

    def test_silero_no_voiced_is_not_second_guessed(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "silero")
        monkeypatch.setattr("server.transcription.vad.silero_available", lambda: True)

        def _silero(buffer):
            return buffer, {"trimmed_ms": 0, "silero_ran": True}

        monkeypatch.setattr("server.transcription.vad.trim_with_silero", _silero)
        original = _wav_bytes(_silence(3) + _tone(0.2, amplitude=0.001) + _silence(3))
        out, meta = prepare_audio(original)
        # Silero kept the audio; the energy VAD must not override it.
        assert out == original
        assert meta["strategy"] == "silero"
        assert meta["trimmed_ms"] == 0

    def test_silero_end_to_end_with_stub_session(self, monkeypatch):
        pytest.importorskip("numpy")
        monkeypatch.setenv("PHLOX_VAD", "silero")
        _patch_silero_session(monkeypatch, _SileroStubSession())
        original = _wav_bytes(_silence(3) + _tone(1.5) + _silence(4))
        out, meta = prepare_audio(original)
        assert meta["strategy"] == "silero"
        assert meta["trimmed_ms"] >= 5000
        assert len(out) < len(original)

    def test_silence_only_keeps_original(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "energy")
        original = _wav_bytes(_silence(2))
        out, meta = prepare_audio(original)
        assert out == original
        assert meta["vad_applied"] is False
