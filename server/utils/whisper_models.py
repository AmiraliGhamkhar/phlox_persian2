"""Catalog and lifecycle management for local automatic speech recognition models.

The desktop app supports multilingual Whisper.cpp weights (official GGML
``.bin`` files plus the whisper.cpp-compatible Q6_K GGUF from
Xviers/whisper-large-v3-turbo-GGUF), the Persian-first Shenava Koochik
tract-streaming ONNX graph, and NVIDIA Parakeet TDT 0.6B v3 INT8 ONNX
(multilingual European, not Persian). All entries use the canonical ASR
terminology; the old module name is retained only because released
clients still import it.
"""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import httpx

from server.constants import DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class DownloadProgress:
    """Rich progress information for model downloads."""

    percentage: float
    downloaded_bytes: int
    total_bytes: int
    speed_bytes_per_sec: float
    eta_seconds: float | None
    current_file: str


class ModelFile(TypedDict):
    """A model artifact downloaded from a public model repository."""

    url: str
    filename: str


class ModelInfo(TypedDict, total=False):
    """Metadata for a local automatic speech recognition model."""

    url: str
    filename: str
    files: list[ModelFile]
    size_mb: int
    description: str
    category: str
    runtime: str
    task: str
    languages: list[str]
    supports_persian: bool
    supports_mixed: bool
    supports_streaming: bool
    display_name: str


WHISPER_CPP_REPO = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
WHISPER_GGUF_REPO = "https://huggingface.co/Xviers/whisper-large-v3-turbo-GGUF/resolve/main"
SHENAVA_REPO = "https://huggingface.co/Reza2kn/Shenava-Koochik-v1.0-tract-streaming/resolve/main"
PARAKEET_REPO = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main"
WHISPER_CPP_WEIGHT_SUFFIXES = {".bin", ".gguf"}

PARAKEET_FILES: list[ModelFile] = [
    {
        "url": f"{PARAKEET_REPO}/decoder_joint-model.int8.onnx",
        "filename": "parakeet-tdt-0.6b-v3-decoder_joint.int8.onnx",
    },
    {
        "url": f"{PARAKEET_REPO}/nemo128.onnx",
        "filename": "parakeet-tdt-0.6b-v3-nemo128.onnx",
    },
    {
        "url": f"{PARAKEET_REPO}/vocab.txt",
        "filename": "parakeet-tdt-0.6b-v3-vocab.txt",
    },
    {
        "url": f"{PARAKEET_REPO}/config.json",
        "filename": "parakeet-tdt-0.6b-v3-config.json",
    },
]

# Whisper large-v3-turbo is multilingual and can decode Persian and English in
# one recording when the language hint is ``auto``. The recommended default is
# the whisper.cpp-subdirectory Q6_K GGUF from Xviers; official ggerganov GGML
# ``.bin`` quants remain available for existing installs.
ASR_MODELS: dict[str, ModelInfo] = {
    "whisper-large-v3-turbo-q6_k": {
        "url": f"{WHISPER_GGUF_REPO}/whisper.cpp/whisper-large-v3-turbo-q6_k.gguf",
        "filename": "whisper-large-v3-turbo-q6_k.gguf",
        "size_mb": 680,
        "description": "Whisper large-v3-turbo Q6_K GGUF — نسخه پیشنهادی whisper.cpp برای فارسی، انگلیسی و گفتار ترکیبی.",
        "category": "whisper.cpp",
        "runtime": "whisper_cpp",
        "task": "transcribe",
        "languages": ["fa", "en"],
        "supports_persian": True,
        "supports_mixed": True,
        "supports_streaming": True,
        "display_name": "Whisper large-v3-turbo (Q6_K GGUF)",
    },
    "whisper-large-v3-turbo": {
        "url": f"{WHISPER_CPP_REPO}/ggml-large-v3-turbo.bin",
        "filename": "ggml-large-v3-turbo.bin",
        "size_mb": 1620,
        "description": "Whisper large-v3-turbo (F16) — مدل چندزبانه برای فارسی، انگلیسی و گفتار ترکیبی؛ موتور whisper.cpp.",
        "category": "whisper.cpp",
        "runtime": "whisper_cpp",
        "task": "transcribe",
        "languages": ["fa", "en"],
        "supports_persian": True,
        "supports_mixed": True,
        "supports_streaming": True,
        "display_name": "Whisper large-v3-turbo (F16)",
    },
    "whisper-large-v3-turbo-q5_0": {
        "url": f"{WHISPER_CPP_REPO}/ggml-large-v3-turbo-q5_0.bin",
        "filename": "ggml-large-v3-turbo-q5_0.bin",
        "size_mb": 574,
        "description": "Whisper large-v3-turbo Q5_0 — نسخه کم‌حجم و چندزبانه برای فارسی، انگلیسی و گفتار ترکیبی.",
        "category": "whisper.cpp",
        "runtime": "whisper_cpp",
        "task": "transcribe",
        "languages": ["fa", "en"],
        "supports_persian": True,
        "supports_mixed": True,
        "display_name": "Whisper large-v3-turbo (Q5_0)",
    },
    "whisper-large-v3-turbo-q8_0": {
        "url": f"{WHISPER_CPP_REPO}/ggml-large-v3-turbo-q8_0.bin",
        "filename": "ggml-large-v3-turbo-q8_0.bin",
        "size_mb": 834,
        "description": "Whisper large-v3-turbo Q8_0 — دقت بالاتر با مصرف حافظه متوسط؛ فارسی، انگلیسی و گفتار ترکیبی.",
        "category": "whisper.cpp",
        "runtime": "whisper_cpp",
        "task": "transcribe",
        "languages": ["fa", "en"],
        "supports_persian": True,
        "supports_mixed": True,
        "supports_streaming": True,
        "display_name": "Whisper large-v3-turbo (Q8_0)",
    },
    "parakeet-tdt-0.6b-v3-int8": {
        "url": f"{PARAKEET_REPO}/encoder-model.int8.onnx",
        "filename": "parakeet-tdt-0.6b-v3-encoder.int8.onnx",
        "files": PARAKEET_FILES,
        "size_mb": 670,
        "description": "Parakeet TDT 0.6B v3 INT8 — مدل چندزبانهٔ کوچک (۲۵ زبان اروپایی). فارسی را پوشش نمی‌دهد.",
        "category": "parakeet",
        "runtime": "parakeet_onnx",
        "task": "transcribe",
        "languages": ["en"],
        "supports_persian": False,
        "supports_mixed": False,
        "supports_streaming": False,
        "display_name": "Parakeet TDT 0.6B v3 (INT8)",
    },
    "parakeet-tdt-0.6b-v3-int8-streaming": {
        "url": f"{PARAKEET_REPO}/encoder-model.int8.onnx",
        "filename": "parakeet-tdt-0.6b-v3-encoder.int8.onnx",
        "files": PARAKEET_FILES,
        "size_mb": 670,
        "description": "Parakeet TDT 0.6B v3 INT8 streaming — همان مدل کوچک با پنجره‌های غلتان برای نمایش زنده. فارسی را پوشش نمی‌دهد.",
        "category": "parakeet",
        "runtime": "parakeet_onnx_streaming",
        "task": "transcribe",
        "languages": ["en"],
        "supports_persian": False,
        "supports_mixed": False,
        "supports_streaming": True,
        "display_name": "Parakeet TDT 0.6B v3 (INT8 streaming)",
    },
    "shenava-koochik-v1.0-int4": {
        "url": f"{SHENAVA_REPO}/model.int4.onnx",
        "filename": "shenava-koochik-v1.0-int4.onnx",
        "files": [
            {
                "url": f"{SHENAVA_REPO}/tokens.txt",
                "filename": "shenava-koochik-v1.0-tokens.txt",
            }
        ],
        "size_mb": 138,
        "description": "Shenava Koochik v1.0 INT4 — مدل بومی فارسی با اجرای محلی و جریانی.",
        "category": "shenava",
        "runtime": "shenava_onnx",
        "task": "transcribe",
        "languages": ["fa"],
        "supports_persian": True,
        "supports_mixed": False,
        "supports_streaming": True,
        "display_name": "Shenava Koochik v1.0 (INT4)",
    },
}

DEFAULT_ASR_MODEL_ID = "whisper-large-v3-turbo-q6_k"

# Backwards-compatible aliases for released clients and older database values.
WHISPER_MODELS = ASR_MODELS
DEFAULT_MODEL_ID = DEFAULT_ASR_MODEL_ID


# ---------------------------------------------------------------------------
# Auxiliary (non-ASR) model artifacts — same download pattern, no selection
# marker: these support the audio pipeline (W2.2 VAD, W2.3 denoise) and are
# always best-effort: a missing artifact means "feature unavailable", and
# callers must fail open to the previous behavior.
# ---------------------------------------------------------------------------


class AuxModelInfo(TypedDict, total=False):
    """Metadata for a small auxiliary model artifact."""

    url: str
    filename: str
    files: list[ModelFile]
    size_mb: int
    description: str


AUX_MODELS: dict[str, AuxModelInfo] = {
    # Silero VAD v5 ONNX (~2 MB) used by the neural silence-trim strategy.
    "silero-vad": {
        "url": "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
        "filename": "silero-vad-v5.onnx",
        "size_mb": 2,
        "description": "Silero VAD v5 — تشخیص مرزهای گفتار برای حذف سکوت ابتدا/انتهاي فایل.",
    },
    # DeepFilterNet3 ONNX bundle (~10 MB) used by optional file denoising.
    "deepfilternet3": {
        "url": "https://huggingface.co/ResembleAI/deepfilternet3-onnx/resolve/main/enc.onnx",
        "filename": "deepfilternet3-enc.onnx",
        "files": [
            {
                "url": "https://huggingface.co/ResembleAI/deepfilternet3-onnx/resolve/main/erb_dec.onnx",
                "filename": "deepfilternet3-erb_dec.onnx",
            },
            {
                "url": "https://huggingface.co/ResembleAI/deepfilternet3-onnx/resolve/main/df_dec.onnx",
                "filename": "deepfilternet3-df_dec.onnx",
            },
        ],
        "size_mb": 10,
        "description": "DeepFilterNet3 — حذف نویز فایل‌های صوتی پیش از پیاده‌سازی.",
    },
}


class AuxModelManager:
    """Download and locate auxiliary model artifacts (VAD / denoise).

    Shares the ASR manager's download pattern but never keeps a selection
    marker: artifacts are either present or not, and every consumer treats a
    missing artifact as "use the previous behavior" (fail open).
    """

    def __init__(self) -> None:
        self.models_dir = DATA_DIR / "aux_models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, artifact_id: str) -> Path | None:
        """Return the primary artifact path when the whole bundle exists."""
        info = AUX_MODELS.get(artifact_id)
        if not info:
            return None
        primary = self.models_dir / info["filename"]
        if not primary.is_file():
            return None
        for extra in info.get("files", []):
            if not (self.models_dir / extra["filename"]).is_file():
                return None
        return primary

    def get_file(self, artifact_id: str, filename: str) -> Path | None:
        """Return a companion file path of a known bundle when present."""
        info = AUX_MODELS.get(artifact_id)
        if not info:
            return None
        known = {info["filename"], *(file["filename"] for file in info.get("files", []))}
        if filename not in known:
            return None
        path = self.models_dir / filename
        return path if path.is_file() else None

    async def ensure_downloaded(self, artifact_id: str) -> Path | None:
        """Download the bundle once (best-effort) and return its path."""
        info = AUX_MODELS.get(artifact_id)
        if not info:
            return None
        existing = self.get_path(artifact_id)
        if existing:
            return existing
        artifacts = [{"url": info["url"], "filename": info["filename"]}, *info.get("files", [])]
        paths = [self.models_dir / artifact["filename"] for artifact in artifacts]
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                follow_redirects=True,
                headers={"User-Agent": "phlox"},
            ) as client:
                for artifact, path in zip(artifacts, paths, strict=True):
                    with suppress(OSError):
                        path.unlink()
                    response = await client.get(artifact["url"])
                    response.raise_for_status()
                    path.write_bytes(response.content)
            logger.info("Downloaded auxiliary model %s", artifact_id)
        except Exception:  # noqa: BLE001 — auxiliary models are best-effort
            for path in paths:
                with suppress(OSError):
                    path.unlink()
            logger.debug("Auxiliary model %s unavailable", artifact_id, exc_info=True)
            return None
        return self.get_path(artifact_id)


aux_model_manager = AuxModelManager()


class ASRModelManager:
    """Download, list, select, and remove local ASR model bundles."""

    def __init__(self):
        self.models_dir = DATA_DIR / "whisper_models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.selection_file = DATA_DIR / "asr_model.txt"

    @staticmethod
    def _public_model(info: ModelInfo, model_id: str, **extra) -> dict:
        return {
            "id": model_id,
            "name": info.get("display_name", model_id),
            "size_mb": info["size_mb"],
            "description": info["description"],
            "url": info["url"],
            "category": info["category"],
            "runtime": info.get("runtime", "unknown"),
            "task": info.get("task", "transcribe"),
            "languages": info.get("languages", []),
            "supports_persian": info.get("supports_persian", False),
            "supports_mixed": info.get("supports_mixed", False),
            "supports_streaming": info.get("supports_streaming", False),
            **extra,
        }

    def get_available_models(self) -> list[dict]:
        """Return the complete local ASR catalog."""
        return [self._public_model(info, model_id) for model_id, info in ASR_MODELS.items()]

    def get_selected_model_id(self) -> str | None:
        """Return the selected downloaded model, if the marker is valid."""
        try:
            selected = self.selection_file.read_text(encoding="utf-8").strip()
        except OSError:
            selected = ""
        info = ASR_MODELS.get(selected)
        if info and (self.models_dir / info["filename"]).exists():
            return selected
        # whisper.cpp sidecar reads a .bin/.gguf filename from this marker.
        for model_id, candidate in ASR_MODELS.items():
            if (
                candidate["filename"] == selected
                and (self.models_dir / candidate["filename"]).exists()
            ):
                return model_id

        # Legacy installations did not have a selection marker. Prefer the
        # requested default and otherwise choose the first downloaded catalog
        # model, without ever selecting an arbitrary unknown file.
        if self.get_model_path(DEFAULT_ASR_MODEL_ID):
            return DEFAULT_ASR_MODEL_ID
        for model_id, candidate in ASR_MODELS.items():
            if (self.models_dir / candidate["filename"]).exists():
                return model_id
        return None

    def select_model(self, model_id: str) -> dict:
        """Select a downloaded model and return its metadata."""
        info = ASR_MODELS.get(model_id)
        if not info:
            raise ValueError(f"Unknown ASR model: {model_id}")
        if not (self.models_dir / info["filename"]).exists():
            raise ValueError(f"ASR model is not downloaded: {model_id}")
        # Tauri's whisper.cpp sidecar accepts a .bin or .gguf filename. ONNX
        # runtimes (Shenava, Parakeet) are executed in Python, so keep the
        # catalog id — a non-weight marker is ignored by the sidecar.
        marker = info["filename"] if info.get("runtime") == "whisper_cpp" else model_id
        self.selection_file.write_text(marker, encoding="utf-8")
        return self._public_model(info, model_id, is_selected=True)

    def get_downloaded_models(self) -> list[dict]:
        """Return downloaded catalog models, including capability metadata."""
        selected_id = self.get_selected_model_id()
        models = []
        # Iterate the catalog so variants that share a primary artifact
        # (Parakeet batch vs streaming) both appear once the bundle is present.
        for model_id, info in ASR_MODELS.items():
            model_file = self.models_dir / info["filename"]
            if not model_file.is_file():
                continue
            size_mb = round(model_file.stat().st_size / (1024 * 1024), 1)
            models.append(
                self._public_model(
                    info,
                    model_id,
                    size_mb=size_mb,
                    path=str(model_file),
                    is_selected=model_id == selected_id,
                    companion_files=[f["filename"] for f in info.get("files", [])],
                )
            )

        return sorted(models, key=lambda model: model["size_mb"])

    def get_model_path(self, model_id: str) -> Path | None:
        """Return the primary artifact path for a known downloaded model."""
        info = ASR_MODELS.get(model_id)
        if not info:
            return None
        model_file = self.models_dir / info["filename"]
        if model_file.exists():
            return model_file
        return None

    async def _download_file(
        self,
        client: httpx.AsyncClient,
        url: str,
        path: Path,
        progress_callback,
        total_offset: int,
        total_size: int,
    ) -> int:
        """Download one artifact while reporting bundle-level progress."""
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            file_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            with path.open("wb") as handle:
                async for chunk in response.aiter_bytes(8192):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size:
                        await progress_callback(
                            DownloadProgress(
                                percentage=((total_offset + downloaded) / total_size) * 100,
                                downloaded_bytes=total_offset + downloaded,
                                total_bytes=total_size,
                                speed_bytes_per_sec=0,
                                eta_seconds=None,
                                current_file=path.name,
                            )
                        )
            return file_size or downloaded

    async def download_model(self, model_id: str, progress_callback=None) -> str:
        """Download a model bundle without deleting other installed models."""
        info = ASR_MODELS.get(model_id)
        if not info:
            raise ValueError(f"Unknown ASR model: {model_id}")

        artifacts = [{"url": info["url"], "filename": info["filename"]}, *info.get("files", [])]
        paths = [self.models_dir / artifact["filename"] for artifact in artifacts]
        primary_path = paths[0]
        if all(path.exists() for path in paths):
            self.select_model(model_id)
            logger.info("ASR model %s already exists", model_id)
            return str(primary_path)

        # Avoid leaving a half-installed bundle selectable after interruption.
        for path in paths:
            with suppress(OSError):
                path.unlink()

        timeout = httpx.Timeout(600.0)
        # Hugging Face signed URLs do not always expose a stable HEAD response.
        # Use the catalog size as a progress denominator; the final event is
        # always forced to 100 percent after the complete bundle is present.
        total_size = max(int(info["size_mb"] * 1024 * 1024), 1)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "phlox"},
            ) as client:
                offset = 0
                for artifact, path in zip(artifacts, paths, strict=True):
                    size = await self._download_file(
                        client,
                        artifact["url"],
                        path,
                        progress_callback,
                        offset,
                        total_size,
                    )
                    offset += size
                    if progress_callback:
                        await progress_callback(
                            DownloadProgress(
                                percentage=min(100, (offset / total_size) * 100),
                                downloaded_bytes=offset,
                                total_bytes=total_size,
                                speed_bytes_per_sec=0,
                                eta_seconds=None,
                                current_file=path.name,
                            )
                        )
            self.select_model(model_id)
            logger.info("Successfully downloaded ASR model %s to %s", model_id, primary_path)
        except (Exception, asyncio.CancelledError):
            # CancelledError included: an SSE client disconnect cancels the
            # download task, and the partial bundle must still be removed.
            for path in paths:
                with suppress(OSError):
                    path.unlink()
            raise

        return str(primary_path)

    def delete_model(self, model_id: str) -> bool:
        """Delete a catalog model and all of its companion artifacts."""
        info = ASR_MODELS.get(model_id)
        if not info:
            return False
        paths = [self.models_dir / info["filename"]] + [
            self.models_dir / file["filename"] for file in info.get("files", [])
        ]
        deleted = False
        for path in paths:
            if path.exists():
                path.unlink()
                deleted = True
                logger.info("Deleted ASR artifact %s", path.name)
        if self.get_selected_model_id() == model_id:
            with suppress(OSError):
                self.selection_file.unlink()
        return deleted

    def get_default_model_path(self) -> Path:
        """Return the default multilingual Whisper model path."""
        return self.models_dir / ASR_MODELS[DEFAULT_ASR_MODEL_ID]["filename"]

    def ensure_default_model_exists(self) -> bool:
        """Check whether the default ASR model exists."""
        return self.get_default_model_path().exists()


WhisperModelManager = ASRModelManager
asr_model_manager = ASRModelManager()
whisper_model_manager = asr_model_manager
