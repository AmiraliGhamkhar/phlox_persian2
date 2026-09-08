"""AssemblyAI Speech-to-Text helpers shared by the batch and realtime adapters.

AssemblyAI differs from the other cloud providers in a few ways that this
module centralises so ``audio.py`` (pre-recorded) and ``live.py`` (realtime)
stay thin:

* **Auth is the raw key, with no ``Bearer`` prefix** (the one exception in the
  codebase is the Anthropic ``x-api-key`` header). Getting this wrong turns
  every request into a 401.
* Pre-recorded jobs use the *plural* ``speech_models`` list, which is a
  *fallback* list (first available model wins), whereas Realtime uses the
  *singular* ``speech_model`` query parameter. They are not interchangeable.
* ``universal-3-5-pro`` natively transcribes 18 languages; for audio in any
  other language (including Persian ``fa``) it automatically falls back to
  ``universal-2`` (99 languages). ``universal-2`` alone is the reliable
  Persian-capable operating point.

Reference (offline snapshot bundled with the integration):
https://www.assemblyai.com/docs/llms.txt — API base URLs, auth, and
``speech_models`` semantics.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

# REST hosts (pre-recorded upload/submit/poll).
ASSEMBLYAI_DEFAULT_URL = "https://api.assemblyai.com"
ASSEMBLYAI_EU_URL = "https://api.eu.assemblyai.com"

# Realtime WebSocket hosts.
ASSEMBLYAI_STREAMING_URL = "wss://streaming.assemblyai.com/v3/ws"
ASSEMBLYAI_EU_STREAMING_URL = "wss://streaming.eu.assemblyai.com/v3/ws"
ASSEMBLYAI_US_STREAMING_URL = "wss://streaming.us.assemblyai.com/v3/ws"

# The app's model field stores a single operating point; expand it to the
# provider's plural pre-recorded fallback list.
_MODEL_SPEECH_MODELS: dict[str, list[str]] = {
    "universal-3-5-pro": ["universal-3-5-pro", "universal-2"],
    "universal-2": ["universal-2"],
}

# Realtime is a narrower set; everything else resolves to the documented
# default ``universal-3-5-pro`` operating point.
_LIVE_MODELS = frozenset({"universal-3-5-pro", "universal-2"})


def assemblyai_api_key(config: dict[str, Any]) -> str:
    """Return the AssemblyAI API key from the canonical ASR key fields."""
    return str(config.get("ASR_KEY") or config.get("WHISPER_KEY") or "").strip()


def assemblyai_rest_url(config: dict[str, Any]) -> str:
    """Resolve the pre-recorded REST base URL.

    Uses the user-configured ``ASR_BASE_URL`` (defaults to the US host that
    ``apply_asr_provider_defaults`` stamps) or ``ASSEMBLYAI_BASE_URL`` env,
    falling back to the documented US API host.
    """
    url = str(config.get("ASR_BASE_URL") or "").strip().rstrip("/")
    if url:
        return url
    url = str(os.environ.get("ASSEMBLYAI_BASE_URL") or "").strip().rstrip("/")
    if url:
        return url
    return ASSEMBLYAI_DEFAULT_URL


def assemblyai_streaming_url(config: dict[str, Any]) -> str:
    """Resolve the realtime WebSocket host for the configured data region.

    AssemblyAI realtime endpoints are separate from the REST host. Prefer an
    explicit ``ASSEMBLYAI_STREAMING_URL`` env override, otherwise infer from
    the configured REST ``ASR_BASE_URL`` host so picking ``api.eu.…`` for file
    transcription also pins realtime audio to the same region.
    """
    url = str(os.environ.get("ASSEMBLYAI_STREAMING_URL") or "").strip().rstrip("/")
    if url:
        return url
    rest = assemblyai_rest_url(config)
    region = _assemblyai_region(rest)
    if region == "eu":
        return ASSEMBLYAI_EU_STREAMING_URL
    if region == "us":
        return ASSEMBLYAI_US_STREAMING_URL
    return ASSEMBLYAI_STREAMING_URL


def _assemblyai_region(url: str) -> str | None:
    """Return the AssemblyAI data region in a REST host, if any.

    Only the region-adjacent subdomain of the ``assemblyai.com`` registrable
    domain is honoured, so a crafted host such as ``eu.evil.example.com`` or
    ``notassemblyai.com`` never selects a regional endpoint.
    """
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    labels = host.split(".")
    if len(labels) < 3 or labels[-2:] != ["assemblyai", "com"]:
        return None
    region = labels[-3]
    if region in {"eu", "us"}:
        return region
    return None


def assemblyai_model(config: dict[str, Any]) -> str:
    """Return the configured operating-point model, defaulting to universal-3-5-pro."""
    model = str(config.get("ASR_MODEL") or config.get("WHISPER_MODEL") or "").strip().lower()
    if not model:
        return "universal-3-5-pro"
    return model


def assemblyai_batch_speech_models(model: str) -> list[str]:
    """Expand a single operating point to the plural pre-recorded fallback list."""
    return list(_MODEL_SPEECH_MODELS.get(model, ["universal-3-5-pro", "universal-2"]))


def assemblyai_live_model(model: str) -> str:
    """Return the singular realtime ``speech_model`` string.

    Pre-recorded-only values (or any unrecognised model) resolve to the
    documented realtime default so a stale/legacy selection never breaks the
    live socket.
    """
    if model in _LIVE_MODELS:
        return model
    return "universal-3-5-pro"
