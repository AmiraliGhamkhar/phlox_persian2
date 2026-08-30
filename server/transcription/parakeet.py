"""Local NVIDIA Parakeet TDT 0.6B v3 INT8 ONNX runtime.

Greedy Token-and-Duration Transducer decoding with no extra Python
dependencies beyond the optional ``onnxruntime`` extra already used by
Shenava. The multilingual 0.6B v3 checkpoint covers 25 European languages
and is **not** a Persian model; Persian speech should use Whisper.cpp or
Shenava instead.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PARAKEET_CACHE: tuple[Any, Any, Any, dict[int, str], int, tuple[str, str, str]] | None = None
_PARAKEET_LOCK = threading.Lock()


def _load_vocab(path: Path) -> tuple[dict[int, str], int]:
    vocab: dict[int, str] = {}
    blank_idx = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip("\n")
        if not line:
            continue
        if " " in line:
            token, _, index = line.rpartition(" ")
            try:
                token_id = int(index)
            except ValueError:
                continue
        else:
            token_id = len(vocab)
            token = line
        vocab[token_id] = token.replace("\u2581", " ")
        if token == "<blk>":
            blank_idx = token_id
    if not vocab:
        raise ValueError("Parakeet vocabulary file is empty")
    if "<blk>" not in vocab.values():
        blank_idx = max(vocab) if vocab else 0
    return vocab, blank_idx


def _load_parakeet_runtime(encoder_path: str, decoder_path: str, preprocessor_path: str):
    """Load ONNX sessions once per model bundle."""
    global _PARAKEET_CACHE
    key = (encoder_path, decoder_path, preprocessor_path)
    with _PARAKEET_LOCK:
        if _PARAKEET_CACHE and _PARAKEET_CACHE[5] == key:
            return _PARAKEET_CACHE[:5]
        try:
            import importlib.util

            if importlib.util.find_spec("numpy") is None:
                raise ImportError("numpy is not installed")
            import onnxruntime as ort
        except ImportError as error:
            raise ValueError(
                "Parakeet support requires the local ONNX runtime in this server build"
            ) from error

        providers = ["CPUExecutionProvider"]
        preprocessor = ort.InferenceSession(preprocessor_path, providers=providers)
        encoder = ort.InferenceSession(encoder_path, providers=providers)
        decoder = ort.InferenceSession(decoder_path, providers=providers)
        vocab_path = Path(encoder_path).with_name("parakeet-tdt-0.6b-v3-vocab.txt")
        if not vocab_path.exists():
            raise ValueError("Parakeet vocabulary file is missing; download the model again")
        vocab, blank_idx = _load_vocab(vocab_path)
        _PARAKEET_CACHE = (preprocessor, encoder, decoder, vocab, blank_idx, key)
        return preprocessor, encoder, decoder, vocab, blank_idx


def _session_feed(session, **named) -> dict[str, Any]:
    """Match provided arrays to the session's actual input names."""
    feed: dict[str, Any] = {}
    leftovers = dict(named)
    for item in session.get_inputs():
        name = item.name
        lowered = name.lower()
        if name in leftovers:
            feed[name] = leftovers.pop(name)
            continue
        match = None
        for key, _ in list(leftovers.items()):
            if key.lower() in lowered or lowered in key.lower():
                match = key
                break
        if match is not None:
            feed[name] = leftovers.pop(match)
    return feed


def _run_named(session, **named):
    feed = _session_feed(session, **named)
    output_names = [item.name for item in session.get_outputs()]
    return dict(zip(output_names, session.run(output_names, feed), strict=False))


def run_parakeet_inference(audio_buffer: bytes, config: dict) -> str:
    """Run greedy TDT decoding over a WAV recording."""
    import numpy as np

    from server.transcription.audio import _read_pcm_wav
    from server.transcription.language import normalize_persian_text
    from server.utils.whisper_models import asr_model_manager

    model_id = str(config.get("ASR_MODEL") or config.get("WHISPER_MODEL") or "")
    info = next(
        (model for model in asr_model_manager.get_available_models() if model["id"] == model_id),
        None,
    )
    if not info or not str(info.get("runtime") or "").startswith("parakeet"):
        raise ValueError("The selected Parakeet model is not downloaded")

    encoder_path = asr_model_manager.get_model_path(model_id)
    if encoder_path is None:
        raise ValueError("The selected Parakeet model is not downloaded")
    models_dir = encoder_path.parent
    decoder_path = models_dir / "parakeet-tdt-0.6b-v3-decoder_joint.int8.onnx"
    preprocessor_path = models_dir / "parakeet-tdt-0.6b-v3-nemo128.onnx"
    if not decoder_path.exists() or not preprocessor_path.exists():
        raise ValueError("Parakeet model bundle is incomplete; download the model again")

    pcm, sample_rate = _read_pcm_wav(audio_buffer)
    if sample_rate != 16000:
        raise ValueError("Parakeet requires 16 kHz audio")
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        return ""

    preprocessor, encoder, decoder, vocab, blank_idx = _load_parakeet_runtime(
        str(encoder_path), str(decoder_path), str(preprocessor_path)
    )

    waveforms = samples[None, :]
    waveforms_len = np.array([samples.size], dtype=np.int64)
    pre_out = _run_named(preprocessor, waveforms=waveforms, waveforms_lens=waveforms_len)
    features = next(value for name, value in pre_out.items() if "len" not in name.lower())
    features_len = next(
        (value for name, value in pre_out.items() if "len" in name.lower()),
        np.array([features.shape[-1]], dtype=np.int64),
    )
    features = np.asarray(features, dtype=np.float32)
    features_len = np.asarray(features_len, dtype=np.int64).reshape(-1)

    enc_out = _run_named(encoder, audio_signal=features, length=features_len)
    encoder_out = next(value for name, value in enc_out.items() if "len" not in name.lower())
    encoder_len = next(
        (value for name, value in enc_out.items() if "len" in name.lower()),
        None,
    )
    encoder_out = np.asarray(encoder_out, dtype=np.float32)
    # NeMo export is [B, D, T]; greedy loop wants [T, D] for a single utterance.
    if encoder_out.ndim == 3:
        if encoder_out.shape[1] > encoder_out.shape[2]:
            encoder_out = np.transpose(encoder_out, (0, 2, 1))
        encodings = encoder_out[0]
    else:
        encodings = encoder_out
    encodings_len = (
        int(np.asarray(encoder_len).reshape(-1)[0])
        if encoder_len is not None
        else encodings.shape[0]
    )
    encodings_len = min(encodings_len, encodings.shape[0])

    shapes = {item.name: item.shape for item in decoder.get_inputs()}
    state1_shape = [
        int(dim) if isinstance(dim, int) else 1 for dim in shapes.get("input_states_1", [2, 1, 640])
    ]
    state2_shape = [
        int(dim) if isinstance(dim, int) else 1 for dim in shapes.get("input_states_2", [2, 1, 640])
    ]
    state1 = np.zeros(state1_shape, dtype=np.float32)
    state2 = np.zeros(state2_shape, dtype=np.float32)

    config_path = models_dir / "parakeet-tdt-0.6b-v3-config.json"
    max_tokens_per_step = 10
    if config_path.exists():
        try:
            parsed = json.loads(config_path.read_text(encoding="utf-8"))
            max_tokens_per_step = int(parsed.get("max_tokens_per_step") or 10)
        except (OSError, ValueError, TypeError):
            pass

    tokens: list[int] = []
    t = 0
    emitted = 0
    vocab_size = len(vocab)
    while t < encodings_len:
        frame = encodings[t]
        dec_out = _run_named(
            decoder,
            encoder_outputs=frame[None, :, None],
            targets=np.array([[tokens[-1] if tokens else blank_idx]], dtype=np.int32),
            target_length=np.array([1], dtype=np.int32),
            input_states_1=state1,
            input_states_2=state2,
        )
        logits = np.asarray(
            next(value for name, value in dec_out.items() if "state" not in name.lower())
        )
        logits = np.squeeze(logits)
        token_logits = logits[:vocab_size]
        duration = 0
        if logits.shape[-1] > vocab_size:
            duration = int(np.argmax(logits[vocab_size:]))
        token = int(np.argmax(token_logits))
        if token != blank_idx:
            next_state1 = next(
                (
                    value
                    for name, value in dec_out.items()
                    if name.endswith("1") and "state" in name.lower()
                ),
                state1,
            )
            next_state2 = next(
                (
                    value
                    for name, value in dec_out.items()
                    if name.endswith("2") and "state" in name.lower()
                ),
                state2,
            )
            state1 = np.asarray(next_state1)
            state2 = np.asarray(next_state2)
            tokens.append(token)
            emitted += 1
        if duration > 0:
            t += duration
            emitted = 0
        elif token == blank_idx or emitted >= max_tokens_per_step:
            t += 1
            emitted = 0

    pieces = [vocab.get(token_id, "") for token_id in tokens]
    text = "".join(pieces)
    text = text.replace("▁", " ").strip()
    from server.transcription.audio import _clean_repetitive_text

    return normalize_persian_text(_clean_repetitive_text(text))
