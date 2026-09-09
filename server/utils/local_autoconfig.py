"""Apply ready-to-use configuration after a local model is downloaded.

Non-technical users should not have to pick providers, URLs, or model ids
after clicking Download. The download endpoints call these helpers so the
next transcription / report request uses the new model immediately.
"""

from __future__ import annotations

import logging

from server.database.config.manager import config_manager
from server.utils.llama_models import PRECONFIGURED_MODELS
from server.utils.whisper_models import ASR_MODELS

logger = logging.getLogger(__name__)


def activate_downloaded_llm(model_id: str) -> dict[str, str]:
    """Switch the app to bundled llama.cpp and the just-downloaded GGUF."""
    info = PRECONFIGURED_MODELS.get(model_id) or {}
    filename = str(info.get("filename") or model_id)
    updates = {
        "LLM_PROVIDER": "local",
        "LLM_BASE_URL": "",
        "PRIMARY_MODEL": filename,
        "SECONDARY_MODEL": filename,
        "REASONING_MODEL": filename,
    }
    config_manager.update_config(updates)
    logger.info("Auto-configured local LLM provider for %s (%s)", model_id, filename)
    return updates


def activate_downloaded_asr(model_id: str) -> dict[str, str]:
    """Switch the app to local ASR and the just-downloaded speech model."""
    if model_id not in ASR_MODELS:
        raise ValueError(f"Unknown ASR model: {model_id}")
    updates = {
        "ASR_PROVIDER": "local",
        "ASR_MODEL": model_id,
        "WHISPER_MODEL": model_id,
        "ASR_BASE_URL": "",
        "WHISPER_BASE_URL": "",
        "ASR_LANGUAGE": "auto",
        "WHISPER_LANGUAGE": "auto",
    }
    config_manager.update_config(updates)
    logger.info("Auto-configured local ASR provider for %s", model_id)
    return updates
