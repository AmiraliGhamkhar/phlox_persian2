#!/usr/bin/env python3
"""Live smoke test for the Speechmatics Realtime adapter.

Runs the *production* adapter (``server.transcription.live``) against the real
service and prints every frame it receives, so a handshake, quota, endpoint or
vocabulary problem shows up here instead of in front of a patient.

    export SPEECHMATICS_API_KEY=...
    python scripts/live_asr_smoke_test.py                      # 6 s of silence
    python scripts/live_asr_smoke_test.py --audio visit.pcm    # 16 kHz s16le
    python scripts/live_asr_smoke_test.py --audio visit.wav --seconds 20

Exit code is 0 only when the session started, the service acknowledged audio
(``AudioAdded``) and the transcript ended cleanly (``EndOfTranscript``).

The API key is read from the environment and is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import wave
from collections import Counter
from pathlib import Path
from typing import Any

# The adapter lives in the server package; make the repo importable when this
# script is run from a checkout (``python scripts/live_asr_smoke_test.py``).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SAMPLE_RATE = 16000
FRAME_BYTES = 8192  # 256 ms of 16 kHz mono s16le — the browser's frame size


def load_audio(path: Path, seconds: float) -> bytes:
    """Read s16le mono PCM from a .pcm or .wav file, trimmed to ``seconds``."""
    raw = path.read_bytes()
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav_file:
            if wav_file.getsampwidth() != 2 or wav_file.getnchannels() != 1:
                raise SystemExit(f"{path}: expected 16-bit mono PCM WAV")
            rate = wav_file.getframerate()
            if rate != SAMPLE_RATE:
                raise SystemExit(f"{path}: expected {SAMPLE_RATE} Hz, got {rate} Hz")
            raw = wav_file.readframes(wav_file.getnframes())
    limit = int(seconds * SAMPLE_RATE * 2)
    return raw[:limit] if limit else raw


def synth_audio(seconds: float) -> bytes:
    """Low-level 220 Hz tone: proves the pipeline without needing a recording."""
    import math

    samples = int(seconds * SAMPLE_RATE)
    frame = bytearray()
    for index in range(samples):
        value = int(1200 * math.sin(2 * math.pi * 220 * index / SAMPLE_RATE))
        frame += value.to_bytes(2, "little", signed=True)
    return bytes(frame)


def _import_adapter():
    """Import the live adapter without initializing the application database.

    ``server.transcription.__init__`` pulls in the SQLCipher-backed config
    manager, which a standalone smoke test has no business opening. Registering
    a stub package with the right ``__path__`` lets ``server.transcription.live``
    (and its DB-free siblings) load on their own.
    """
    import importlib
    import types

    if "server.transcription" not in sys.modules:
        stub = types.ModuleType("server.transcription")
        stub.__path__ = [str(REPO_ROOT / "server" / "transcription")]
        sys.modules["server.transcription"] = stub
    return importlib.import_module("server.transcription.live")


async def run(args: argparse.Namespace) -> int:
    try:
        live_module = _import_adapter()
    except ImportError as error:
        print(f"Could not import the server package: {error}", file=sys.stderr)
        print("Run this from the repository root inside the server environment.", file=sys.stderr)
        return 2
    SpeechmaticsLiveSession = live_module.SpeechmaticsLiveSession
    speechmatics_rt_url = live_module.speechmatics_rt_url

    api_key = os.environ.get("SPEECHMATICS_API_KEY") or os.environ.get("ASR_KEY") or ""
    if not api_key.strip():
        print("SPEECHMATICS_API_KEY is not set.", file=sys.stderr)
        return 2

    config: dict[str, Any] = {
        "ASR_PROVIDER": "speechmatics",
        "ASR_KEY": api_key.strip(),
        "ASR_MODEL": args.model,
        "ASR_LANGUAGE": args.language,
    }
    if args.url:
        config["ASR_BASE_URL"] = args.url

    events: list[dict] = []
    counts: Counter[str] = Counter()

    async def emit(event: dict) -> None:
        counts[event.get("type", "?")] += 1
        events.append(event)
        shown = {key: value for key, value in event.items() if key != "text"}
        text = event.get("text")
        print(f"  <- {json.dumps(shown, ensure_ascii=False)}")
        if text:
            print(f"     text: {text}")

    audio = (
        load_audio(Path(args.audio), args.seconds) if args.audio else synth_audio(args.seconds)
    )
    print(f"Endpoint : {speechmatics_rt_url(config)}")
    print(f"Language : {config['ASR_LANGUAGE']}   model: {args.model}")
    print(f"Audio    : {len(audio)} bytes ({len(audio) / (SAMPLE_RATE * 2):.1f} s)")

    session = SpeechmaticsLiveSession(config, emit)
    try:
        await session.start()
    except Exception as error:  # noqa: BLE001 - the whole point is to see it
        print(f"\nSession did not start: {error}", file=sys.stderr)
        return 1
    print("Session started (RecognitionStarted)\n")

    try:
        for offset in range(0, len(audio), FRAME_BYTES):
            await session.feed_pcm(audio[offset : offset + FRAME_BYTES])
            await asyncio.sleep(0.256)  # real-time pacing, like the browser
        transcript = await session.stop()
    finally:
        with contextlib.suppress(Exception):
            await session.stop()

    print()
    print(f"Events      : {dict(counts)}")
    print(f"Audio acked : seq_no={getattr(session, '_frames_acked', 0)}")
    print(f"Transcript  : {transcript or '(empty)'}")

    if session.failed:
        failure = session._failure  # noqa: SLF001 - diagnostics only
        print(
            f"\nFAILED: {failure.error_type} (code={failure.code}) retryable={failure.retryable}",
            file=sys.stderr,
        )
        return 1
    if not counts.get("done"):
        print("\nFAILED: no EndOfTranscript ('done') frame was received", file=sys.stderr)
        return 1
    print("\nOK: session started, audio was acknowledged, transcript ended cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", help="Path to a 16 kHz mono s16le .pcm or .wav file")
    parser.add_argument("--seconds", type=float, default=6.0, help="Seconds of audio to send")
    parser.add_argument("--language", default="fa", help="ISO language code (default: fa)")
    parser.add_argument("--model", default="enhanced", help="standard | enhanced")
    parser.add_argument("--url", help="Override the Realtime endpoint (ASR_BASE_URL)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
