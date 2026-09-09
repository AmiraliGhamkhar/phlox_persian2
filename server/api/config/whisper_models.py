"""
ASR model management API endpoints.

Provides backwards-compatible Whisper routes and canonical ASR routes for downloading, listing, and deleting models.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from server.constants import IS_DOCKER
from server.database.config.manager import config_manager
from server.utils.whisper_models import asr_model_manager

router = APIRouter()
logger = logging.getLogger(__name__)


def _restart_asr_server_background() -> None:
    """Restart the local ASR server without blocking the HTTP response."""
    import threading

    def _run() -> None:
        try:
            from server.utils.local_servers import restart_asr_server

            restart_asr_server()
        except Exception:
            logger.debug("Background ASR restart skipped", exc_info=True)

    threading.Thread(target=_run, name="asr-restart", daemon=True).start()


@router.get("/local/asr/models/available")
@router.get("/local/whisper/models/available")
async def get_available_whisper_models():
    """Get list of available ASR models for download."""
    models = asr_model_manager.get_available_models()
    return {"models": models}


@router.get("/local/asr/models/downloaded")
@router.get("/local/whisper/models/downloaded")
async def get_downloaded_whisper_models():
    """Get list of downloaded ASR models."""
    models = asr_model_manager.get_downloaded_models()
    return {"models": models}


@router.post("/local/asr/models/download")
@router.post("/local/whisper/models/download")
async def download_whisper_model(
    model_id: str = Body(..., embed=True, description="ASR model ID to download"),
):
    """Download an ASR model."""
    try:
        path = await asr_model_manager.download_model(model_id)
        from server.utils.local_autoconfig import activate_downloaded_asr

        activate_downloaded_asr(model_id)
        _restart_asr_server_background()
        return {
            "message": "Model downloaded successfully",
            "path": path,
            "auto_configured": True,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error downloading model {model_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to download model") from e


@router.get("/local/asr/models/download/stream")
@router.get("/local/whisper/models/download/stream")
async def download_whisper_model_stream(model_id: str):
    """Stream ASR model download progress using SSE."""
    if not model_id:
        raise HTTPException(status_code=422, detail="model_id is required")

    async def generate():
        queue = asyncio.Queue()

        async def progress_callback(progress):
            """Callback to queue progress events."""
            await queue.put(
                {
                    "type": "progress",
                    "percentage": progress.percentage,
                    "downloaded_bytes": progress.downloaded_bytes,
                    "total_bytes": progress.total_bytes,
                    "speed_bytes_per_sec": progress.speed_bytes_per_sec,
                    "eta_seconds": progress.eta_seconds,
                    "current_file": progress.current_file,
                }
            )

        # Start download in background task
        download_task = asyncio.create_task(
            asr_model_manager.download_model(model_id, progress_callback=progress_callback)
        )

        # Send start event
        yield f"data: {json.dumps({'type': 'start', 'model_id': model_id})}\n\n"

        try:
            while not download_task.done():
                try:
                    progress = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(progress)}\n\n"
                except TimeoutError:
                    # Send keepalive to prevent connection timeout
                    yield ": keepalive\n\n"

            # Get final result
            downloaded_path = await download_task
            from server.utils.local_autoconfig import activate_downloaded_asr

            activate_downloaded_asr(model_id)
            _restart_asr_server_background()
            yield f"data: {json.dumps({'type': 'complete', 'path': downloaded_path, 'auto_configured': True})}\n\n"

        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"Download error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred during download'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/local/asr/models/select")
@router.post("/local/whisper/models/select")
async def select_whisper_model(
    model_id: str = Body(..., embed=True, description="Downloaded ASR model ID"),
):
    """Select the local ASR model used by the next transcription request."""
    try:
        selected = asr_model_manager.select_model(model_id)
        # Keep the encrypted application configuration and the plaintext
        # process-manager marker synchronized. Legacy aliases remain readable.
        config_manager.update_config(
            {
                "ASR_PROVIDER": "local",
                "ASR_MODEL": model_id,
                "WHISPER_MODEL": model_id,
                "ASR_BASE_URL": "",
                "WHISPER_BASE_URL": "",
            }
        )
        _restart_asr_server_background()
        return {"model": selected}
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/local/asr/models/{model_id}")
@router.delete("/local/whisper/models/{model_id}")
async def delete_whisper_model(model_id: str):
    """Delete a downloaded ASR model."""
    success = asr_model_manager.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"message": "Model deleted successfully"}


@router.get("/local/asr/status")
@router.get("/local/whisper/status")
async def get_whisper_status():
    """Get status of local ASR installation (works in desktop and Docker)."""
    from server.utils.local_servers import asr_server_running, local_runtime_available

    models = asr_model_manager.get_downloaded_models()
    default_exists = asr_model_manager.ensure_default_model_exists()

    return {
        "available": len(models) > 0,
        "models": models,
        "models_count": len(models),
        "default_model_exists": default_exists,
        "models_dir": str(asr_model_manager.models_dir),
        "server_running": asr_server_running(),
        "runtime": local_runtime_available(),
        "is_docker": IS_DOCKER,
    }


@router.get("/local/asr/model-recommendations")
@router.get("/local/whisper/model-recommendations")
async def get_whisper_model_recommendations():
    """Return the complete curated local ASR catalog for easy model switching."""
    recommendations = []
    for model in asr_model_manager.get_available_models():
        is_recommended = model["id"] == "whisper-large-v3-turbo-q6_k"
        badge = None
        if is_recommended:
            badge = "⭐ پیشنهادشده"
        elif model["id"].startswith("parakeet-") and model.get("supports_streaming"):
            badge = "زنده"
        elif model["id"].startswith("parakeet-"):
            badge = "کوچک"
        elif not model.get("supports_persian"):
            badge = "بدون فارسی"
        recommendations.append(
            {
                **model,
                "simple_name": model["name"],
                "size": f"{model['size_mb']}MB",
                "recommendedType": "recommended" if is_recommended else "alternative",
                "badge": badge,
                "badge_color": "purple" if is_recommended else None,
            }
        )
    return {"models": recommendations}
