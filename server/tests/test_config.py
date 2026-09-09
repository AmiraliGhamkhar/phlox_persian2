"""
Tests for configuration endpoints.
Uses TestClient and checks JSON response structure.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.config import router

app = FastAPI()
app.include_router(router, prefix="/api/config")
client = TestClient(app)


def is_valid_json(response):
    try:
        response.json()
        return True
    except ValueError:
        return False


def test_get_config():
    response = client.get("/api/config/global")
    assert response.status_code == 200
    assert is_valid_json(response)
    data = response.json()
    # Expect config to be a dict
    assert isinstance(data, dict)


def test_validate_url_accepts_named_providers():
    response = client.get(
        "/api/config/validate-url",
        params={"url": "http://127.0.0.1:11434", "type": "ollama"},
    )
    assert response.status_code == 200
    assert "valid" in response.json()


def test_get_all_options():
    response = client.get("/api/config/options")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_update_config():
    new_config = {"SECONDARY_MODEL": "test_value"}
    response = client.post("/api/config/global", json=new_config)
    assert response.status_code == 200
    data = response.json()
    message = data.get("message", "")
    assert "message" in data and ("success" in message.lower())


def test_update_config_rejects_unknown_keys():
    """Mass-assignment guard: arbitrary config keys must be rejected."""
    response = client.post("/api/config/global", json={"TEST_CONFIG": "test_value"})
    assert response.status_code == 400
    assert "Unknown configuration keys" in response.json()["detail"]


def test_update_config_rejects_metadata_url():
    """URL fields must pass the SSRF guard before being stored."""
    response = client.post(
        "/api/config/global",
        json={"LLM_BASE_URL": "http://169.254.169.254/latest/meta-data"},
    )
    assert response.status_code == 400
    assert "LLM_BASE_URL" in response.json()["detail"]


def test_update_config_rejects_bad_language():
    response = client.post("/api/config/global", json={"ASR_LANGUAGE": "de"})
    assert response.status_code == 400
    assert "ASR_LANGUAGE" in response.json()["detail"]


def test_update_options():
    new_options = {"TEST_OPTION": "test_option_value"}
    response = client.post("/api/config/options/TEST_CATEGORY", json=new_options)
    assert response.status_code == 200
    data = response.json()
    assert "updated" in data.get("message", "").lower()


def test_get_asr_models_fireworks_catalog():
    response = client.get("/api/config/asr/models", params={"provider": "fireworks"})
    assert response.status_code == 200
    data = response.json()
    assert data["listAvailable"] is True
    assert "fireworks-asr-v2" in data["models"]


def test_get_asr_models_assemblyai_catalog():
    response = client.get("/api/config/asr/models", params={"provider": "assemblyai"})
    assert response.status_code == 200
    data = response.json()
    assert data["listAvailable"] is True
    assert "universal-3-5-pro" in data["models"]


def test_get_asr_models_speechmatics_catalog():
    response = client.get("/api/config/asr/models", params={"provider": "speechmatics"})
    assert response.status_code == 200
    data = response.json()
    assert data["listAvailable"] is True
    assert "enhanced" in data["models"]


def test_get_asr_models_local_does_not_require_endpoint():
    response = client.get("/api/config/asr/models", params={"provider": "local"})
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "listAvailable" in data


def test_validate_url_fireworks_llm_is_openai_compatible():
    """Fireworks is both an LLM and ASR provider; LLM probes must not use Whisper."""
    from server.api.config.validation import _normalize_validation_type

    assert _normalize_validation_type("fireworks") == "openai"
    assert _normalize_validation_type("groq") == "openai"
    assert _normalize_validation_type("openrouter") == "openai"
    assert _normalize_validation_type("whisper") == "whisper"
    assert _normalize_validation_type("assemblyai") == "whisper"
    assert _normalize_validation_type("anthropic") == "anthropic"


def test_get_providers_catalog():
    response = client.get("/api/config/providers")
    assert response.status_code == 200
    data = response.json()
    assert "llm" in data and "asr" in data
    llm_ids = {item["id"] for item in data["llm"]}
    assert "ollama" in llm_ids
    assert "anthropic" in llm_ids
    asr_ids = {item["id"] for item in data["asr"]}
    assert "fireworks" in asr_ids
    assert "speechmatics" in asr_ids
    assert "assemblyai" in asr_ids
    assert "local" in asr_ids
    assert "groq" in llm_ids
    assert "openrouter" in llm_ids


def test_reset_options_to_defaults():
    response = client.post("/api/config/options/reset-to-defaults")
    assert response.status_code == 200
    data = response.json()
    assert "reset" in data.get("message", "").lower()
