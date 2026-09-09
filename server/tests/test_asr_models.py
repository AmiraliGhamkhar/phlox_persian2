"""Tests for the local ASR catalog, including Parakeet and whisper.cpp markers."""

from server.utils.whisper_models import (
    ASR_MODELS,
    DEFAULT_ASR_MODEL_ID,
    SHENAVA_REPO,
    WHISPER_GGUF_REPO,
    ASRModelManager,
)


def test_catalog_wires_xviers_q6k_and_shenava_tract_streaming():
    whisper = ASR_MODELS["whisper-large-v3-turbo-q6_k"]
    assert DEFAULT_ASR_MODEL_ID == "whisper-large-v3-turbo-q6_k"
    assert whisper["filename"] == "whisper-large-v3-turbo-q6_k.gguf"
    assert whisper["url"] == (f"{WHISPER_GGUF_REPO}/whisper.cpp/whisper-large-v3-turbo-q6_k.gguf")
    assert whisper["runtime"] == "whisper_cpp"
    assert whisper["supports_persian"] is True

    shenava = ASR_MODELS["shenava-koochik-v1.0-int4"]
    assert shenava["url"] == f"{SHENAVA_REPO}/model.int4.onnx"
    assert shenava["filename"] == "shenava-koochik-v1.0-int4.onnx"
    assert shenava["runtime"] == "shenava_onnx"
    assert shenava["files"][0]["url"] == f"{SHENAVA_REPO}/tokens.txt"
    assert shenava["files"][0]["filename"] == "shenava-koochik-v1.0-tokens.txt"
    assert "Reza2kn/Shenava-Koochik-v1.0-tract-streaming" in SHENAVA_REPO
    assert "Xviers/whisper-large-v3-turbo-GGUF" in WHISPER_GGUF_REPO


def test_catalog_includes_whisper_turbo_and_parakeet():
    assert "whisper-large-v3-turbo-q5_0" in ASR_MODELS
    assert "parakeet-tdt-0.6b-v3-int8" in ASR_MODELS
    assert "parakeet-tdt-0.6b-v3-int8-streaming" in ASR_MODELS
    assert ASR_MODELS["parakeet-tdt-0.6b-v3-int8"]["supports_persian"] is False
    assert ASR_MODELS["whisper-large-v3-turbo-q5_0"]["supports_persian"] is True
    assert ASR_MODELS["parakeet-tdt-0.6b-v3-int8-streaming"]["supports_streaming"] is True


def test_select_model_writes_whisper_cpp_filename(tmp_path):
    manager = ASRModelManager()
    manager.models_dir = tmp_path
    manager.selection_file = tmp_path / "asr_model.txt"
    filename = ASR_MODELS["whisper-large-v3-turbo-q5_0"]["filename"]
    (tmp_path / filename).write_bytes(b"ggml")
    selected = manager.select_model("whisper-large-v3-turbo-q5_0")
    assert selected["id"] == "whisper-large-v3-turbo-q5_0"
    assert manager.selection_file.read_text(encoding="utf-8") == filename
    assert manager.get_selected_model_id() == "whisper-large-v3-turbo-q5_0"


def test_select_onnx_model_writes_catalog_id(tmp_path):
    manager = ASRModelManager()
    manager.models_dir = tmp_path
    manager.selection_file = tmp_path / "asr_model.txt"
    filename = ASR_MODELS["parakeet-tdt-0.6b-v3-int8"]["filename"]
    (tmp_path / filename).write_bytes(b"onnx")
    manager.select_model("parakeet-tdt-0.6b-v3-int8")
    assert manager.selection_file.read_text(encoding="utf-8") == "parakeet-tdt-0.6b-v3-int8"
    assert manager.get_selected_model_id() == "parakeet-tdt-0.6b-v3-int8"


def test_downloaded_models_lists_shared_parakeet_variants(tmp_path):
    manager = ASRModelManager()
    manager.models_dir = tmp_path
    manager.selection_file = tmp_path / "asr_model.txt"
    filename = ASR_MODELS["parakeet-tdt-0.6b-v3-int8"]["filename"]
    (tmp_path / filename).write_bytes(b"onnx")
    ids = {model["id"] for model in manager.get_downloaded_models()}
    assert "parakeet-tdt-0.6b-v3-int8" in ids
    assert "parakeet-tdt-0.6b-v3-int8-streaming" in ids


def test_legacy_model_id_marker_still_resolves(tmp_path):
    manager = ASRModelManager()
    manager.models_dir = tmp_path
    manager.selection_file = tmp_path / "asr_model.txt"
    filename = ASR_MODELS["whisper-large-v3-turbo-q8_0"]["filename"]
    (tmp_path / filename).write_bytes(b"ggml")
    manager.selection_file.write_text("whisper-large-v3-turbo-q8_0", encoding="utf-8")
    assert manager.get_selected_model_id() == "whisper-large-v3-turbo-q8_0"


def test_select_q6k_gguf_writes_filename_marker(tmp_path):
    manager = ASRModelManager()
    manager.models_dir = tmp_path
    manager.selection_file = tmp_path / "asr_model.txt"
    filename = ASR_MODELS["whisper-large-v3-turbo-q6_k"]["filename"]
    (tmp_path / filename).write_bytes(b"gguf")
    selected = manager.select_model("whisper-large-v3-turbo-q6_k")
    assert selected["id"] == "whisper-large-v3-turbo-q6_k"
    assert manager.selection_file.read_text(encoding="utf-8") == filename
    assert manager.get_selected_model_id() == "whisper-large-v3-turbo-q6_k"


def test_whisper_sidecar_resolves_gguf_and_ignores_onnx(tmp_path, monkeypatch):
    import server.utils.local_servers as local_servers

    monkeypatch.setattr(local_servers, "DATA_DIR", tmp_path)
    models_dir = tmp_path / "whisper_models"
    models_dir.mkdir()
    (models_dir / "shenava-koochik-v1.0-int4.onnx").write_bytes(b"onnx")
    assert local_servers._whisper_model_path() is None

    gguf = models_dir / "whisper-large-v3-turbo-q6_k.gguf"
    gguf.write_bytes(b"ggml")
    (tmp_path / "asr_model.txt").write_text(gguf.name, encoding="utf-8")
    assert local_servers._whisper_model_path() == gguf
