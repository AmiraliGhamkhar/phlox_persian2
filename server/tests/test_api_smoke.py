"""End-to-end smoke of every live HTTP API the three-page app uses."""

import pytest
from fastapi.testclient import TestClient

from server.server import initialize_and_get_app
from server.utils.local_request_token import set_request_token

TEST_TOKEN = "e2e-api-smoke-token"


@pytest.fixture(scope="module")
def client():
    set_request_token(TEST_TOKEN)
    return TestClient(
        initialize_and_get_app(),
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )


GET_OK = [
    "/health",
    "/api/health",
    "/version",
    "/api/dashboard/health",
    "/api/workspace/specialties",
    "/api/workspace/status",
    "/api/workspace/dictionary",
    "/api/config/global",
    "/api/config/options",
    "/api/config/providers",
    "/api/config/user",
    "/api/config/status",
    "/api/config/local/models/available",
    "/api/config/local/models",
    "/api/config/local/status",
    "/api/config/local/selected-model",
    "/api/config/local/model-recommendations",
    "/api/config/local/asr/models/available",
    "/api/config/local/asr/models/downloaded",
    "/api/config/local/asr/status",
    "/api/config/local/asr/model-recommendations",
    "/api/config/local/whisper/models/available",
    "/api/config/local/whisper/status",
]


@pytest.mark.parametrize("path", GET_OK)
def test_get_endpoints_succeed(client, path):
    response = client.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code} {response.text}"
    assert response.headers["content-type"].startswith("application/json")


def test_health_and_version_shape(client):
    assert client.get("/health").json() == {"status": "ok"}
    version = client.get("/version").json()
    assert version["name"] == "Phlox"
    assert version["version"]


def test_user_settings_are_never_json_null(client):
    data = client.get("/api/config/user").json()
    assert isinstance(data["name"], str)
    assert isinstance(data["specialty"], str)


def test_user_settings_roundtrip(client):
    original = client.get("/api/config/user").json()
    response = client.post(
        "/api/config/user",
        json={"name": "دکتر آزمون", "specialty": "cardiology"},
    )
    assert response.status_code == 200, response.text
    saved = client.get("/api/config/user").json()
    assert saved["name"] == "دکتر آزمون"
    assert saved["specialty"] == "cardiology"
    client.post("/api/config/user", json=original)


def test_config_roundtrip_allowlisted_key(client):
    response = client.post("/api/config/global", json={"ASR_LANGUAGE": "fa"})
    assert response.status_code == 200, response.text
    config = client.get("/api/config/global").json()
    assert config["ASR_LANGUAGE"] == "fa"
    client.post("/api/config/global", json={"ASR_LANGUAGE": "auto"})


def test_llm_and_asr_model_listings(client):
    local_llm = client.get("/api/config/llm/models", params={"provider": "local"})
    assert local_llm.status_code == 200
    assert "models" in local_llm.json()

    fireworks = client.get("/api/config/asr/models", params={"provider": "fireworks"})
    assert fireworks.status_code == 200
    assert fireworks.json()["listAvailable"] is True

    missing = client.get("/api/config/asr/models")
    assert missing.status_code == 422


def test_report_and_dictate_reject_empty(client):
    empty_report = client.post("/api/workspace/report", json={"transcript": "   "})
    assert empty_report.status_code in {400, 422}

    missing_file = client.post("/api/transcribe/dictate")
    assert missing_file.status_code in {400, 422}


def test_dictionary_search(client):
    response = client.get("/api/workspace/dictionary", params={"q": "fever", "limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["matches"]
    assert data["total"] >= 1


def test_unknown_api_is_404(client):
    response = client.get("/api/definitely-missing")
    assert response.status_code == 404
