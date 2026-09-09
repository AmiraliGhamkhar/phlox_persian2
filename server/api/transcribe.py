"""Speech-to-text API for the simplified three-page app.

Two endpoints, no patient record required:

* ``POST /dictate`` — transcribe one recorded audio file.
* ``WS /live`` — stream PCM audio and receive partial / final transcripts.
"""

import json
import logging
import secrets

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from server.transcription.audio import transcribe_audio
from server.utils.request_limits import (
    MAX_AUDIO_UPLOAD_BYTES,
    read_upload_limited,
)

router = APIRouter()

# WebSocket handshake subprotocol for live transcription. The request token is
# carried as a second offered subprotocol so it never appears in the request
# URL/query string (query strings are written to uvicorn access logs and, via
# the desktop process manager, to the on-disk app log — A09:2025).
LIVE_WS_SUBPROTOCOL = "phlox-live"


def _authorize_live_socket(websocket: WebSocket) -> bool:
    """Accept a Bearer header or ``Sec-WebSocket-Protocol`` subprotocol.

    Browsers cannot set an Authorization header on the WebSocket handshake,
    so the desktop client offers ``phlox-live,<token>`` as subprotocols; the
    token is compared with constant-time equality and is never placed in the
    URL or query string.
    """
    from server.constants import is_docker_runtime
    from server.utils.local_request_token import get_request_token

    if is_docker_runtime():
        return True
    expected = get_request_token()
    if not expected:
        return False
    header = websocket.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return secrets.compare_digest(header[7:].strip(), expected)

    offered = websocket.headers.get("sec-websocket-protocol") or ""
    protocols = [p.strip() for p in offered.split(",") if p.strip()]
    if LIVE_WS_SUBPROTOCOL not in protocols:
        return False
    return any(
        secrets.compare_digest(protocol, expected)
        for protocol in protocols
        if protocol != LIVE_WS_SUBPROTOCOL
    )


@router.websocket("/live")
async def live_transcribe(websocket: WebSocket):
    """Stream PCM audio and receive partial / final transcripts.

    Client frames:
    - binary: 16-bit little-endian mono PCM at 16 kHz
    - text JSON ``{"type": "flush"}`` to finalize the pending utterance
    - text JSON ``{"type": "stop"}`` to finish

    Server frames (JSON text):
    - ``{"type": "ready", "authoritative": bool, "features": {...}}``
    - ``{"type": "partial"|"final", "text": str, "speaker"?: str, "forced"?: bool}``
    - ``{"type": "utterance_end", "forced": bool}``
    - ``{"type": "info", "info_type": str, ...}``
    - ``{"type": "warning", "warning_type": str, "message": str, "authoritative"?: bool}``
    - ``{"type": "error", "error_type": str, "message": str, "fatal": true,
       "retryable": bool, "authoritative": false}``
    - ``{"type": "done"}`` when the engine finished the transcript

    ``authoritative: false`` (on ``error``/``warning``) tells the client that the
    live text no longer covers the whole recording, so the full audio must still
    be batch-transcribed instead of being replaced by the partial live text.
    """
    if not _authorize_live_socket(websocket):
        await websocket.close(code=4401)
        return
    # Echo the app subprotocol (never the token) so the client can confirm the
    # negotiated connection.
    offered = websocket.headers.get("sec-websocket-protocol") or ""
    subprotocol = (
        LIVE_WS_SUBPROTOCOL
        if LIVE_WS_SUBPROTOCOL in [p.strip() for p in offered.split(",") if p.strip()]
        else None
    )
    await websocket.accept(subprotocol=subprotocol)

    from server.database.config.manager import config_manager
    from server.transcription.live import create_live_session, live_is_authoritative

    config = config_manager.get_config()

    async def emit(event: dict) -> None:
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            logging.debug("Live transcript emit failed", exc_info=True)

    session = create_live_session(config, emit)
    try:
        await session.start()
        ready: dict = {"type": "ready", "authoritative": live_is_authoritative(config)}
        settings = getattr(session, "settings", None)
        if settings is not None:
            ready["features"] = settings.as_features()
        await emit(ready)
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data:
                await session.feed_pcm(data)
                continue
            text = message.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "stop":
                break
            if payload.get("type") == "flush":
                # Finalize the pending utterance (sent when the clinician
                # pauses) without ending the session.
                await session.flush()
                continue
    except WebSocketDisconnect:
        logging.debug("Live transcription client disconnected")
    except Exception as error:
        logging.error("Live transcription failed: %s", error)
        try:
            await emit({"type": "error", "message": str(error)})
        except Exception:
            logging.debug("Could not send live transcription error", exc_info=True)
    finally:
        try:
            final_text = await session.stop()
            if final_text:
                await emit({"type": "final", "text": final_text})
        except Exception:
            logging.debug("Live transcription shutdown failed", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            logging.debug("Live transcription websocket already closed", exc_info=True)


@router.post("/dictate")
async def dictate(file: UploadFile = File(...)):
    """Transcribe one recorded audio file (workspace recorder)."""
    try:
        audio_buffer = await read_upload_limited(file, MAX_AUDIO_UPLOAD_BYTES, "Audio upload")

        transcription_result = await transcribe_audio(audio_buffer)
        transcript_text = str(transcription_result["text"])
        transcription_duration = float(transcription_result["transcriptionDuration"])

        return {
            "transcription": transcript_text,
            "transcriptionDuration": transcription_duration,
        }
    except Exception as e:
        logging.error(f"Error occurred during dictation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
