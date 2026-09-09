"""Server-side denoise (W2.3) — SNR gating, fail-open paths, sequencing.

Weight-dependent acceptance (real MUSAN clips through DeepFilterNet3) is
manual-run via ``scripts/eval_asr.py`` — the sandbox/CI never downloads
model weights, so these tests exercise the gate and the mock/no-weights
paths only.
"""

import io
import math
import random
import wave
from array import array

import pytest

from server.transcription.denoise import (
    denoise_mode,
    denoise_wav,
    estimate_snr_db,
    max_snr_db,
)
from server.transcription.hygiene import prepare_audio


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


def _noisy_bursts(tone_amp: float, noise_amp: float, seconds: float = 2.0, seed: int = 3) -> bytes:
    """Alternating tone+noise / noise-only bursts.

    The SNR pre-estimate works on VAD-style voiced labels, so it needs the
    temporal speech-vs-noise contrast of real recordings (a constant mix has
    no label contrast and estimates None).
    """
    rng = random.Random(seed)
    burst = int(0.25 * 16000)
    chunks: list[int] = []
    for block in range(int(seconds / 0.25)):
        voiced = block % 2 == 0
        for i in range(burst):
            tone = (
                tone_amp * math.sin(2 * math.pi * 440 * (block * burst + i) / 16000)
                if voiced
                else 0.0
            )
            noise = noise_amp * rng.uniform(-1, 1)
            chunks.append(int(32767 * max(-1.0, min(1.0, tone + noise))))
    return array("h", chunks).tobytes()


# ------------------------------------------------------------------ SNR gate


class TestSnrEstimate:
    def test_clean_clip_has_high_snr(self):
        snr = estimate_snr_db(_noisy_bursts(0.3, 0.01), 16000)
        assert snr is not None and snr >= 20

    def test_noisy_clip_has_low_snr(self):
        snr = estimate_snr_db(_noisy_bursts(0.3, 0.11), 16000)
        assert snr is not None and snr < 12

    def test_constant_tone_has_no_contrast(self):
        assert estimate_snr_db(_tone(2.0), 16000) is None

    def test_silence_only_is_none(self):
        assert estimate_snr_db(b"\x00\x00" * 32000, 16000) is None

    def test_too_short_is_none(self):
        assert estimate_snr_db(_tone(0.05), 16000) is None


class TestSettings:
    def test_mode_validation(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "bogus")
        assert denoise_mode() == "auto"
        monkeypatch.setenv("PHLOX_DENOISE", "ON")
        assert denoise_mode() == "on"

    def test_max_snr_clamped(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE_MAX_SNR_DB", "999")
        assert max_snr_db() == 60.0
        monkeypatch.setenv("PHLOX_DENOISE_MAX_SNR_DB", "-999")
        assert max_snr_db() == -20.0
        monkeypatch.setenv("PHLOX_DENOISE_MAX_SNR_DB", "nonsense")
        assert max_snr_db() == 12.0
        monkeypatch.setenv("PHLOX_DENOISE_MAX_SNR_DB", "8")
        assert max_snr_db() == 8.0


# ---------------------------------------------------------------- fail open


class TestDenoiseGate:
    def test_off_never_applies(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "off")
        original = _wav_bytes(_noisy_bursts(0.3, 0.11))
        out, meta = denoise_wav(original)
        assert out == original
        assert meta == {"denoise_applied": False, "snr_estimate_db": None}

    def test_auto_skips_clean_clip(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "auto")
        original = _wav_bytes(_tone(2.0))
        calls = []

        def _counting_backend(pcm, rate):
            assert pcm
            calls.append(rate)
            return None

        out, meta = denoise_wav(original, backend=_counting_backend)
        assert out == original
        assert meta["denoise_applied"] is False
        assert calls == []  # SNR gate prevented the backend entirely

    def test_auto_applies_on_noisy_clip_with_backend(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "auto")
        original = _wav_bytes(_noisy_bursts(0.3, 0.11))

        def fake_backend(pcm, rate):
            assert rate == 16000
            return pcm  # identity "enhancement"

        out, meta = denoise_wav(original, backend=fake_backend)
        assert meta["denoise_applied"] is True
        assert meta["snr_estimate_db"] is not None and meta["snr_estimate_db"] < 12
        # Output is a valid WAV of the same duration.
        with wave.open(io.BytesIO(out), "rb") as wav:
            assert wav.getframerate() == 16000
            assert wav.getnframes() == 2 * 16000

    def test_on_ignores_snr_gate(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        original = _wav_bytes(_tone(2.0))
        out, meta = denoise_wav(original, backend=lambda pcm, _rate: pcm)
        assert meta["denoise_applied"] is True

    def test_backend_unavailable_fails_open(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        original = _wav_bytes(_noisy_bursts(0.3, 0.11))
        out, meta = denoise_wav(original, backend=lambda _pcm, _rate: None)
        assert out == original
        assert meta["denoise_applied"] is False

    def test_backend_error_fails_open(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        original = _wav_bytes(_noisy_bursts(0.3, 0.11))

        def broken_backend(pcm, rate):
            assert pcm and rate == 16000
            raise RuntimeError("onnx exploded")

        out, meta = denoise_wav(original, backend=broken_backend)
        assert out == original
        assert meta["denoise_applied"] is False

    def test_real_backend_without_weights_is_none(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        # No monkeypatched backend: the real one must fail open (weights are
        # never present in CI).
        original = _wav_bytes(_noisy_bursts(0.3, 0.11))
        out, meta = denoise_wav(original)
        assert out == original
        assert meta["denoise_applied"] is False

    def test_garbage_input_fails_open(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        junk = b"this is not audio at all"
        out, meta = denoise_wav(junk)
        assert out == junk and meta["denoise_applied"] is False

    def test_wrong_size_backend_output_rejected(self, monkeypatch):
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        original = _wav_bytes(_noisy_bursts(0.3, 0.11))
        out, meta = denoise_wav(original, backend=lambda pcm, _rate: pcm[:-100])
        assert out == original
        assert meta["denoise_applied"] is False


# --------------------------------------------------- denoise -> VAD -> ASR


class TestSequencing:
    def test_denoise_runs_before_vad_in_prepare_audio(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "energy")
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        order: list[str] = []

        def fake_denoise(buffer):
            order.append("denoise")
            return buffer, {"denoise_applied": False, "snr_estimate_db": None}

        def fake_energy(buffer):
            order.append("vad")
            return buffer, {"trimmed_ms": 0}

        monkeypatch.setattr("server.transcription.denoise.denoise_wav", fake_denoise)
        monkeypatch.setattr("server.transcription.hygiene.trim_silence_wav", fake_energy)
        monkeypatch.setattr("server.transcription.vad.silero_available", lambda: False)
        prepare_audio(_wav_bytes(_tone(1.0)))
        assert order == ["denoise", "vad"]

    def test_denoised_buffer_feeds_vad(self, monkeypatch):
        monkeypatch.setenv("PHLOX_VAD", "energy")
        monkeypatch.setenv("PHLOX_DENOISE", "on")
        enhanced = _wav_bytes(_tone(1.0))
        seen: dict[str, bytes] = {}

        def fake_denoise(_buffer):
            return enhanced, {"denoise_applied": True, "snr_estimate_db": 3.0}

        def fake_energy(buffer):
            seen["vad_input"] = buffer
            return buffer, {"trimmed_ms": 0}

        monkeypatch.setattr("server.transcription.denoise.denoise_wav", fake_denoise)
        monkeypatch.setattr("server.transcription.hygiene.trim_silence_wav", fake_energy)
        monkeypatch.setattr("server.transcription.vad.silero_available", lambda: False)
        out, meta = prepare_audio(_wav_bytes(_noisy_bursts(0.3, 0.11)))
        assert seen["vad_input"] == enhanced
        assert meta["denoise_applied"] is True
        assert meta["snr_estimate_db"] == 3.0

    @pytest.mark.asyncio
    async def test_transcribe_audio_prepares_before_asr(self, monkeypatch):
        from server.transcription import audio

        order: list[str] = []

        def fake_prepare(buffer):
            order.append(f"prepare:{len(buffer)}")
            return buffer, {"vad_applied": False, "trimmed_ms": 0, "strategy": None}

        async def fake_engine(buffer, config, bias_terms=None):
            order.append(f"asr:{len(buffer)}:{config.get('ASR_MODEL')}:{bias_terms is None}")
            return {"text": "سلام", "transcriptionDuration": 0.1}

        monkeypatch.setattr(audio, "prepare_audio", fake_prepare)
        monkeypatch.setattr(audio, "_transcribe_external_api", fake_engine)
        monkeypatch.setattr(
            "server.utils.providers.resolve_asr_connection",
            lambda _config: {"provider": "openai_compatible", "protocol": "openai", "model": "m"},
        )
        monkeypatch.setattr(
            "server.database.config.manager.config_manager.get_config",
            lambda: {"ASR_BASE_URL": "http://127.0.0.1:9999", "ASR_MODEL": "m"},
        )
        result = await audio.transcribe_audio(b"RIFF....WAVEfake")
        assert order[0].startswith("prepare:")
        assert order[1].startswith("asr:")
        assert result["itn_applied"] is False
        assert "vad" in result
