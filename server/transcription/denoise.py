"""Optional server-side denoising for file transcription — W2.3.

Sequencing inside ``prepare_audio`` is **denoise → VAD → ASR**: a noisy
upload is enhanced before silence trimming and transcription, while the
original buffer is always kept available for rollback.

Gate (fail open, never blocks transcription):

* ``PHLOX_DENOISE=auto`` (default): run the denoiser only when the frame
  energy SNR pre-estimate on VAD-style voiced labels is below
  ``PHLOX_DENOISE_MAX_SNR_DB`` (default 12 dB) — clean clips are untouched.
* ``on``: always run when the backend is available.
* ``off``: never run (A/B baseline).

Missing optional extra (numpy/onnxruntime), missing DeepFilterNet3 weights,
or any backend error ⇒ the input is returned unchanged with a debug log.
Result metadata: ``{"denoise_applied": bool, "snr_estimate_db": float|None}``.

The backend follows DeepFilterNet3's exported ONNX interface (enc / erb_dec
/ df_dec; see the DeepFilterNet project's export documentation). The weights
are a small CPU bundle fetched through the auxiliary model manager; downloading
them is an explicit operator action, so this module never blocks on the
network inside a request.
"""

from __future__ import annotations

import io
import logging
import math
import os
import wave

logger = logging.getLogger(__name__)

_FRAME_MS = 30
_MAX_SNR_DEFAULT_DB = 12.0
_MAX_SNR_RANGE_DB = (-20.0, 60.0)
_DF_SAMPLE_RATE = 48000
_DF_HOP = 480
_DF_WIN = 960
_DF_ERB_BINS = 32
_DF_BINS = 96
_DF_ORDER = 5
_DENOISE_ARTIFACT_ID = "deepfilternet3"


def denoise_mode() -> str:
    """Validated ``PHLOX_DENOISE`` value (default ``auto``)."""
    raw = str(os.environ.get("PHLOX_DENOISE", "auto")).strip().lower()
    return raw if raw in {"auto", "on", "off"} else "auto"


def max_snr_db() -> float:
    """Clamped ``PHLOX_DENOISE_MAX_SNR_DB`` (invalid values keep the default)."""
    try:
        value = float(os.environ.get("PHLOX_DENOISE_MAX_SNR_DB", _MAX_SNR_DEFAULT_DB))
    except (TypeError, ValueError):
        return _MAX_SNR_DEFAULT_DB
    return min(_MAX_SNR_RANGE_DB[1], max(_MAX_SNR_RANGE_DB[0], value))


# ---------------------------------------------------------------------------
# Frame-energy SNR pre-estimate on VAD-style voiced labels
# ---------------------------------------------------------------------------


def _frame_rms(frames: bytes, frame_bytes: int) -> list[float]:
    import array

    energies: list[float] = []
    for start in range(0, len(frames) - frame_bytes + 1, frame_bytes):
        samples = array.array("h")
        samples.frombytes(frames[start : start + frame_bytes])
        if not samples:
            continue
        total = sum(s * s for s in samples)
        energies.append(math.sqrt(total / len(samples)) / 32768.0)
    return energies


def estimate_snr_db(pcm: bytes, rate: int) -> float | None:
    """Speech-vs-noise ratio in dB from frame energies (VAD-style labels).

    Returns None when the estimate is not meaningful (all-voiced, all-silent
    or too short), which the auto gate treats as "clean enough".
    """
    frame_bytes = max(2, int(rate * _FRAME_MS / 1000) * 2)
    energies = _frame_rms(pcm, frame_bytes)
    if len(energies) < 5:
        return None
    ordered = sorted(energies)
    floor = ordered[max(0, int(len(ordered) * 0.2))]
    threshold = max(floor * 3.0, floor + 0.004, 0.0025)
    speech = [e * e for e in energies if e >= threshold]
    noise = [e * e for e in energies if e < threshold]
    if not speech or not noise:
        return None
    mean_speech = sum(speech) / len(speech)
    mean_noise = sum(noise) / len(noise)
    if mean_noise <= 0 or mean_speech <= 0:
        return None
    return 10.0 * math.log10(mean_speech / mean_noise)


# ---------------------------------------------------------------------------
# WAV plumbing (mirrors the VAD's fail-open helpers)
# ---------------------------------------------------------------------------


def _read_mono_wav(audio_bytes: bytes) -> tuple[bytes, int] | None:
    import array

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            if wav.getcomptype() != "NONE" or wav.getsampwidth() != 2:
                return None
            rate = wav.getframerate()
            channels = wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        return None
    if channels == 1:
        return frames, rate
    samples = array.array("h")
    samples.frombytes(frames[: (len(frames) // 2) * 2])
    mono = array.array(
        "h",
        (
            (left + right) // 2
            for left, right in zip(samples[::channels], samples[1::channels], strict=False)
        ),
    )
    return mono.tobytes(), rate


def _wrap_wav(pcm: bytes, rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav_out:
        wav_out.setnchannels(1)
        wav_out.setsampwidth(2)
        wav_out.setframerate(rate)
        wav_out.writeframes(pcm)
    return out.getvalue()


# ---------------------------------------------------------------------------
# DeepFilterNet3 ONNX backend (best-effort, fully fail-open)
# ---------------------------------------------------------------------------


def _df3_sessions():
    """Load the three DF3 graphs, or None when the backend is unavailable."""
    try:
        import importlib.util

        if (
            importlib.util.find_spec("numpy") is None
            or importlib.util.find_spec("onnxruntime") is None
        ):
            logger.debug("Denoise backend unavailable: optional extra not installed")
            return None
        import onnxruntime as ort

        from server.utils.whisper_models import aux_model_manager

        primary = aux_model_manager.get_path(_DENOISE_ARTIFACT_ID)
        if primary is None:
            logger.debug("Denoise backend unavailable: DeepFilterNet3 weights not downloaded")
            return None
        enc = primary
        erb_dec = aux_model_manager.get_file(_DENOISE_ARTIFACT_ID, "deepfilternet3-erb_dec.onnx")
        df_dec = aux_model_manager.get_file(_DENOISE_ARTIFACT_ID, "deepfilternet3-df_dec.onnx")
        if erb_dec is None or df_dec is None:
            return None
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        providers = ["CPUExecutionProvider"]
        return (
            ort.InferenceSession(str(enc), opts, providers=providers),
            ort.InferenceSession(str(erb_dec), opts, providers=providers),
            ort.InferenceSession(str(df_dec), opts, providers=providers),
        )
    except Exception:  # noqa: BLE001 — denoise must never break ASR
        logger.debug("Denoise backend failed to load", exc_info=True)
        return None


def _resample_linear(samples, src_rate: int, dst_rate: int):
    import numpy as np

    if src_rate == dst_rate:
        return samples
    positions = np.arange(int(len(samples) * dst_rate / src_rate), dtype=np.float64)
    positions *= src_rate / dst_rate
    indices = np.floor(positions).astype(np.int64)
    frac = (positions - indices).astype(np.float32)
    indices = np.clip(indices, 0, len(samples) - 1)
    nxt = np.clip(indices + 1, 0, len(samples) - 1)
    return samples[indices] * (1.0 - frac) + samples[nxt] * frac


def _df3_enhance(sessions, samples_f32, rate: int):
    """Run the DF3 enhancement loop; returns enhanced samples or raises."""
    import numpy as np

    enc, erb_dec, df_dec = sessions
    samples48 = _resample_linear(samples_f32, rate, _DF_SAMPLE_RATE)
    if samples48.size < _DF_WIN:
        samples48 = np.pad(samples48, (0, _DF_WIN - samples48.size))

    window = np.hanning(_DF_WIN).astype(np.float32)
    n_frames = 1 + max(0, (samples48.size - _DF_WIN) // _DF_HOP)
    frames = np.lib.stride_tricks.sliding_window_view(samples48, _DF_WIN)[::_DF_HOP][:n_frames]
    spectrum = np.fft.rfft(frames * window, axis=1)  # [T, 481]

    # ERB features: log power in 32 bands spanning 0..24 kHz (approximate
    # libDF's geometric band edges), normalised like the reference features.
    band_edges = np.geomspace(1.0, _DF_SAMPLE_RATE / 2, _DF_ERB_BINS + 1).astype(int)
    band_edges = np.clip(band_edges, 0, spectrum.shape[1] - 1)
    power = np.abs(spectrum) ** 2
    erb = np.zeros((n_frames, _DF_ERB_BINS), dtype=np.float32)
    for band in range(_DF_ERB_BINS):
        lo, hi = band_edges[band], max(band_edges[band] + 1, band_edges[band + 1])
        erb[:, band] = power[:, lo:hi].mean(axis=1)
    feat_erb = np.clip((np.log10(erb + 1e-10) + 8.0) / 10.0, -1.5, 0.5)

    # Complex spectral features of the first 96 bins, unit-normalised.
    low = spectrum[:, :_DF_BINS]
    norm = np.abs(low) + 1e-8
    feat_spec = np.stack([low.real / norm, low.imag / norm], axis=1).astype(np.float32)

    e0, e1, e2, e3, emb, c0, _lsnr = enc.run(
        None,
        {
            "feat_erb": feat_erb[None, None, :, :],
            "feat_spec": feat_spec[None, :, :, :],
        },
    )
    erb_mask = erb_dec.run(None, {"emb": emb, "e3": e3, "e2": e2, "e1": e1, "e0": e0})[0]
    coefs = df_dec.run(None, {"emb": emb, "c0": c0})[0]

    gains_erb = np.clip(np.asarray(erb_mask)[0, 0], 0.0, 1.0)  # [T, 32]
    freq_of_bin = np.arange(spectrum.shape[1])
    band_index = np.searchsorted(band_edges, freq_of_bin, side="right") - 1
    band_index = np.clip(band_index, 0, _DF_ERB_BINS - 1)
    full_gain = gains_erb[:, band_index]

    enhanced = spectrum * full_gain
    # Deep filtering on the upper bands: y[t,f] = Σ_k coef[t,k,f]·x[t-k,f].
    coefs = np.asarray(coefs)[0]  # [T, df_order, nb_df, 2]
    if coefs.shape[1] == _DF_ORDER and coefs.shape[2] == _DF_BINS:
        coef_c = coefs[..., 0] + 1j * coefs[..., 1]  # [T, K, 96]
        upper = spectrum[:, _DF_BINS:]
        deep = np.zeros_like(upper)
        for tap in range(_DF_ORDER):
            shifted = upper.copy()
            if tap:
                shifted[tap:] = upper[:-tap]
                shifted[:tap] = 0.0
            deep += coef_c[:, tap, :] * shifted
        enhanced[:, _DF_BINS:] = deep

    synth = np.fft.irfft(enhanced, n=_DF_WIN, axis=1) * window
    output_len = (n_frames - 1) * _DF_HOP + _DF_WIN
    out = np.zeros(output_len, dtype=np.float32)
    norm = np.zeros(output_len, dtype=np.float32)
    for index in range(n_frames):
        start = index * _DF_HOP
        out[start : start + _DF_WIN] += synth[index]
        norm[start : start + _DF_WIN] += window * window
    out /= np.maximum(norm, 1e-8)
    out16 = _resample_linear(out[: samples48.size], _DF_SAMPLE_RATE, rate)
    return np.clip(out16 * 32768.0, -32768, 32767).astype(np.int16).tobytes()


def _apply_backend(pcm: bytes, rate: int) -> bytes | None:
    """Enhance 16-bit mono PCM; None on any problem (fail open)."""
    sessions = _df3_sessions()
    if sessions is None:
        return None
    try:
        import numpy as np

        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        enhanced = _df3_enhance(sessions, samples, rate)
        if enhanced is None or len(enhanced) != len(pcm):
            return None
        return enhanced
    except Exception:  # noqa: BLE001 — denoise must never break ASR
        logger.debug("DeepFilterNet3 enhancement failed; keeping original audio", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def denoise_wav(audio_bytes: bytes, backend=None) -> tuple[bytes, dict]:
    """Denoise a WAV buffer when the gate allows it.

    Returns ``(bytes, {"denoise_applied": bool, "snr_estimate_db": float|None})``.
    Never raises; any problem returns the input unchanged (fail open).
    ``backend`` is a test seam with the same ``(pcm, rate) -> bytes|None``
    contract as the DeepFilterNet3 runner.
    """
    meta: dict = {"denoise_applied": False, "snr_estimate_db": None}
    mode = denoise_mode()
    if mode == "off" or not audio_bytes:
        return audio_bytes, meta
    try:
        decoded = _read_mono_wav(audio_bytes)
        if decoded is None:
            return audio_bytes, meta
        frames, rate = decoded
        snr = estimate_snr_db(frames, rate)
        meta["snr_estimate_db"] = None if snr is None else round(snr, 1)
        if mode == "auto" and (snr is None or snr >= max_snr_db()):
            return audio_bytes, meta  # clean enough: leave the audio untouched
        runner = backend or _apply_backend
        enhanced = runner(frames, rate)
        if enhanced is None or len(enhanced) != len(frames):
            return audio_bytes, meta  # backend unavailable/misbehaving: fail open
        return _wrap_wav(enhanced, rate), {**meta, "denoise_applied": True}
    except Exception:  # noqa: BLE001 — denoise must never break ASR
        logger.debug("Denoise pre-pass failed; keeping original audio", exc_info=True)
        return audio_bytes, meta
