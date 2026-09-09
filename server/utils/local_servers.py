"""Supervise bundled llama.cpp / whisper.cpp servers when no sidecar manager exists.

The Tauri desktop app spawns ``phlox-llama-server`` / ``phlox-whisper-server``
from its Rust process manager. Docker images ship the same binaries (see the
Dockerfile ``local-runtime`` stage) but have no Rust side, so the API server
supervises them itself:

* :func:`ensure_llm_server` / :func:`ensure_asr_server` start the binary on
  the allocated loopback port when the matching provider is ``local`` and a
  model file is downloaded.
* The model download/select endpoints call the ``restart_*`` helpers so the
  freshly downloaded model is picked up immediately.
* Everything is best-effort and safely no-ops when binaries or models are
  missing (desktop keeps using the Rust sidecar; only Docker auto-starts).

The spawn arguments mirror ``src-tauri/src/pm.rs`` so behaviour is identical
in both runtimes.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from server.constants import DATA_DIR, IS_DOCKER
from server.utils.whisper_models import WHISPER_CPP_WEIGHT_SUFFIXES

logger = logging.getLogger(__name__)

LLAMA_BIN_ENV = "PHLOX_LLAMA_SERVER_BIN"
WHISPER_BIN_ENV = "PHLOX_WHISPER_SERVER_BIN"

_LLAMA_CANDIDATES = ("phlox-llama-server", "llama-server")
_WHISPER_CANDIDATES = ("phlox-whisper-server", "whisper-server")

_lock = threading.Lock()
_processes: dict[str, subprocess.Popen] = {}


def _find_binary(env_var: str, candidates: tuple[str, ...]) -> Path | None:
    """Locate a server binary via env override, PATH, or /usr/local/bin."""
    override = (os.environ.get(env_var) or "").strip()
    if override:
        path = Path(override)
        if path.is_file() and os.access(path, os.X_OK):
            return path
        logger.warning("%s points at a missing binary: %s", env_var, override)
    for name in candidates:
        found = shutil.which(name)
        if found:
            return Path(found)
        fallback = Path("/usr/local/bin") / name
        if fallback.is_file() and os.access(fallback, os.X_OK):
            return fallback
    return None


def llama_server_binary() -> Path | None:
    """Return the llama-server binary path, or None when unavailable."""
    return _find_binary(LLAMA_BIN_ENV, _LLAMA_CANDIDATES)


def whisper_server_binary() -> Path | None:
    """Return the whisper-server binary path, or None when unavailable."""
    return _find_binary(WHISPER_BIN_ENV, _WHISPER_CANDIDATES)


def local_runtime_available() -> dict[str, bool]:
    """Report which bundled inference binaries exist in this runtime."""
    return {
        "llama_server": llama_server_binary() is not None,
        "whisper_server": whisper_server_binary() is not None,
    }


def _llm_model_path() -> Path | None:
    """Mirror the Rust ``find_llama_model`` resolution order."""
    models_dir = DATA_DIR / "llm_models"
    selection = DATA_DIR / "llm_model.txt"
    try:
        name = selection.read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
    if name and "/" not in name and "\\" not in name:
        candidate = models_dir / name
        if candidate.suffix == ".gguf" and candidate.exists():
            return candidate
    try:
        entries = sorted(models_dir.glob("*.gguf"))
    except OSError:
        return None
    for path in entries:
        if "mmproj" not in path.name.lower():
            return path
    return None


def _llm_mmproj_path() -> Path | None:
    models_dir = DATA_DIR / "llm_models"
    try:
        matches = sorted(models_dir.glob("*mmproj*.gguf"))
    except OSError:
        return None
    return matches[0] if matches else None


def _is_whisper_cpp_weight(path: Path) -> bool:
    """True for whisper.cpp GGML/GGUF weights; ONNX graphs are Python-only."""
    return path.suffix.lower() in WHISPER_CPP_WEIGHT_SUFFIXES


def _whisper_model_path() -> Path | None:
    """Mirror the Rust ``find_whisper_model`` resolution order (.bin/.gguf)."""
    models_dir = DATA_DIR / "whisper_models"
    selection = DATA_DIR / "asr_model.txt"
    try:
        name = selection.read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
    if name and "/" not in name and "\\" not in name:
        candidate = models_dir / name
        if _is_whisper_cpp_weight(candidate) and candidate.exists():
            return candidate
    try:
        entries = sorted(
            path for path in models_dir.iterdir() if path.is_file() and _is_whisper_cpp_weight(path)
        )
    except OSError:
        return None
    return entries[0] if entries else None


def _probe(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310
            return 200 <= response.status < 500
    except Exception:
        return False


def _llm_health_url() -> str:
    from server.utils.allocated_ports import get_llama_port

    return f"http://127.0.0.1:{get_llama_port()}/health"


def _asr_health_url() -> str:
    from server.utils.allocated_ports import get_whisper_port

    return f"http://127.0.0.1:{get_whisper_port()}/health"


def llm_server_running() -> bool:
    """True when something answers the llama health endpoint."""
    return _probe(_llm_health_url())


def asr_server_running() -> bool:
    """True when something answers the whisper health endpoint."""
    return _probe(_asr_health_url())


def _spawn_logged(name: str, argv: list[str]) -> subprocess.Popen | None:
    logger.info("Starting %s: %s", name, " ".join(argv))
    try:
        return subprocess.Popen(  # nosec B603 - argv is fully constructed here
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as error:
        logger.warning("Could not start %s: %s", name, error)
        return None


def _wait_healthy(name: str, url: str, proc: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            logger.warning("%s exited during startup (code %s)", name, proc.returncode)
            return False
        if _probe(url):
            return True
        time.sleep(1.0)
    logger.warning("%s did not become healthy in %.0fs", name, timeout)
    return False


def _beam_size() -> int:
    try:
        value = int((os.environ.get("PHLOX_ASR_BEAM_SIZE") or "1").strip())
    except ValueError:
        return 1
    return min(10, max(1, value))


def ensure_llm_server(*, wait: float = 90.0) -> bool:
    """Start the bundled llama-server if it is not already listening.

    Only Docker auto-starts (desktop uses the Rust sidecar). Returns True
    when the health endpoint answers.
    """
    if llm_server_running():
        return True
    if not IS_DOCKER:
        return False
    binary = llama_server_binary()
    model = _llm_model_path()
    if binary is None or model is None:
        return False
    from server.utils.allocated_ports import get_llama_port

    argv = [
        str(binary),
        "--port",
        str(get_llama_port()),
        "--host",
        "127.0.0.1",
        "--model",
        str(model),
        "--ctx-size",
        "16384",
        "--jinja",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
    ]
    if "qwen3" in model.name.lower():
        argv += ["--chat-template-kwargs", '{"enable_thinking": false}']
    mmproj = _llm_mmproj_path()
    if mmproj is not None:
        argv += ["--mmproj", str(mmproj)]
    with _lock:
        proc = _spawn_logged("llama-server", argv)
        if proc is None:
            return False
        _processes["llama"] = proc
    return _wait_healthy("llama-server", _llm_health_url(), proc, wait)


def ensure_asr_server(*, wait: float = 60.0) -> bool:
    """Start the bundled whisper-server if it is not already listening."""
    if asr_server_running():
        return True
    if not IS_DOCKER:
        return False
    binary = whisper_server_binary()
    model = _whisper_model_path()
    if binary is None or model is None:
        return False
    from server.utils.allocated_ports import get_whisper_port

    argv = [
        str(binary),
        "--port",
        str(get_whisper_port()),
        "--host",
        "127.0.0.1",
        "--model",
        str(model),
        "--beam-size",
        str(_beam_size()),
        "--suppress-nst",
    ]
    with _lock:
        proc = _spawn_logged("whisper-server", argv)
        if proc is None:
            return False
        _processes["whisper"] = proc
    return _wait_healthy("whisper-server", _asr_health_url(), proc, wait)


def _stop(name: str) -> None:
    with _lock:
        proc = _processes.pop(name, None)
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            logger.debug("Could not stop %s", name, exc_info=True)


def stop_local_servers() -> None:
    """Stop servers this supervisor started (shutdown hook)."""
    _stop("llama")
    _stop("whisper")


def restart_llm_server() -> bool:
    """Restart llama-server so a new model file is picked up (Docker)."""
    if not IS_DOCKER:
        return llm_server_running()
    _stop("llama")
    # The Rust sidecar is absent in Docker; a foreign listener would only
    # exist if the operator runs their own server — leave it alone.
    if llm_server_running():
        return True
    ok = ensure_llm_server()
    if ok:
        return True
    # ensure_* returns False when already-healthy was missed by a race;
    # re-probe once before reporting failure.
    time.sleep(1.0)
    return llm_server_running()


def restart_asr_server() -> bool:
    """Restart whisper-server so a new model file is picked up (Docker)."""
    if not IS_DOCKER:
        return asr_server_running()
    _stop("whisper")
    if asr_server_running():
        return True
    ok = ensure_asr_server()
    if ok:
        return True
    time.sleep(1.0)
    return asr_server_running()


def ensure_configured_local_servers() -> dict[str, bool]:
    """Start whichever local servers the saved config asks for.

    Called once at startup (Docker) and after downloads. Never raises.
    """
    result = {"llm": False, "asr": False}
    if not IS_DOCKER:
        result["llm"] = llm_server_running()
        result["asr"] = asr_server_running()
        return result
    try:
        from server.database.config.manager import config_manager

        config = config_manager.get_config()
    except Exception:
        logger.debug("Local server autostart skipped (config unavailable)", exc_info=True)
        return result
    try:
        if (config.get("LLM_PROVIDER") or "") == "local":
            result["llm"] = ensure_llm_server(wait=30.0)
        else:
            result["llm"] = llm_server_running()
        asr_provider = config.get("ASR_PROVIDER") or ""
        asr_model = config.get("ASR_MODEL") or config.get("WHISPER_MODEL") or ""
        # ONNX runtimes (Shenava, Parakeet) run in-process — no sidecar.
        needs_sidecar = asr_provider == "local" and not str(asr_model).startswith(
            ("shenava-", "parakeet-")
        )
        if needs_sidecar:
            result["asr"] = ensure_asr_server(wait=30.0)
        else:
            result["asr"] = asr_server_running()
    except Exception:
        logger.debug("Local server autostart failed", exc_info=True)
    return result
