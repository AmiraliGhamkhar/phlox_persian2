"""Tests for the local ASR catalog, including Parakeet and whisper.cpp markers."""

from server.utils.whisper_models import ASR_MODELS, ASRModelManager


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
