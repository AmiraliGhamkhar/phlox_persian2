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
