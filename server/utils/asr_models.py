"""Canonical automatic speech recognition model API.

The original module is named ``whisper_models`` for backwards compatibility
with released clients. New code should import ASR names from this module.
"""

from server.utils.whisper_models import (
    ASR_MODELS,
    DEFAULT_ASR_MODEL_ID,
    ASRModelManager,
    asr_model_manager,
)

__all__ = [
    "ASR_MODELS",
    "DEFAULT_ASR_MODEL_ID",
    "ASRModelManager",
    "asr_model_manager",
]
