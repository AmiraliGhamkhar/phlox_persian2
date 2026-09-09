"""Tests for the simplified specialty / dictionary / report workspace."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import workspace
from server.nlp_tools.report import compose_full_note, specialty_label
from server.nlp_tools.specialties import SPECIALTIES
from server.schemas.workspace import ClinicalReport
from server.utils.local_autoconfig import activate_downloaded_asr, activate_downloaded_llm

app = FastAPI()
app.include_router(workspace.router, prefix="/api/workspace")
client = TestClient(app)


def test_list_specialties_returns_persian_cards():
    response = client.get("/api/workspace/specialties")
    assert response.status_code == 200
    data = response.json()
    assert len(data["specialties"]) == len(SPECIALTIES)
    first = data["specialties"][0]
    assert first["fa"]
    assert first["id"]
    assert "پزشکی" in " ".join(item["fa"] for item in data["specialties"])


def test_workspace_status_shape():
    response = client.get("/api/workspace/status")
    assert response.status_code == 200
    data = response.json()
    for key in ("specialty", "name", "llm_ready", "asr_ready", "llm_provider", "asr_provider"):
        assert key in data


def test_asr_ready_requires_url_for_openai_compatible():
    from server.api.workspace import _asr_ready, _llm_ready

    leftover_local_model = {
        "ASR_PROVIDER": "openai_compatible",
        "ASR_MODEL": "whisper-large-v3-turbo-q6_k",
    }
    assert _asr_ready(leftover_local_model) is False
    assert _asr_ready(
        {"ASR_PROVIDER": "openai_compatible", "ASR_BASE_URL": "http://127.0.0.1:2022"}
    )
    assert _asr_ready({"ASR_PROVIDER": "local"}) is True
    assert _asr_ready({"ASR_PROVIDER": "assemblyai"}) is False
    assert _asr_ready({"ASR_PROVIDER": "assemblyai", "ASR_KEY": "k"}) is True
    assert _asr_ready({"ASR_PROVIDER": "openai", "ASR_KEY": "sk"}) is True
    assert _llm_ready({"LLM_PROVIDER": "groq", "LLM_API_KEY": "gsk"}) is True
    assert _llm_ready({"LLM_PROVIDER": "openai"}) is False


def test_dictionary_search_persian_and_english():
    empty = client.get("/api/workspace/dictionary")
    assert empty.status_code == 200
    assert empty.json()["total"] >= 1500

    fa = client.get("/api/workspace/dictionary", params={"q": "تب", "limit": 5})
    assert fa.status_code == 200
    matches = fa.json()["matches"]
    assert matches
    assert any("fever" in item["en"].lower() or item["fa"] == "تب" for item in matches)

    en = client.get("/api/workspace/dictionary", params={"q": "hypertension", "limit": 5})
    assert en.status_code == 200
    assert en.json()["matches"]


def test_generate_report_rejects_empty_transcript():
    response = client.post(
        "/api/workspace/report",
        json={"transcript": "   ", "specialty": "Cardiology"},
    )
    assert response.status_code == 422 or response.status_code == 400


@pytest.mark.asyncio
async def test_generate_report_uses_specialty_and_dictionary():
    fake_report = ClinicalReport(
        chief_complaint="درد قفسه سینه",
        history="درد از دیروز شروع شده است",
        examination="",
        assessment="درد قفسه سینه نیازمند بررسی",
        plan="۱. نوار قلب",
        full_note="",
    )

    async def fake_chat(**_kwargs):
        return {"message": {"content": fake_report.model_dump_json()}}

    mock_client = AsyncMock()
    mock_client.chat = fake_chat

    with (
        patch("server.nlp_tools.report.get_llm_client", return_value=mock_client),
        patch(
            "server.nlp_tools.report.config_manager.get_config",
            return_value={"PRIMARY_MODEL": "gpt-4o", "LLM_PROVIDER": "openai"},
        ),
        patch(
            "server.nlp_tools.report.config_manager.get_user_settings",
            return_value={"specialty": "Cardiology", "name": "دکتر آزمون"},
        ),
        patch(
            "server.nlp_tools.report.config_manager.get_prompts_and_options",
            return_value={"options": {"general": {"temperature": 0.0}}},
        ),
    ):
        response = client.post(
            "/api/workspace/report",
            json={
                "transcript": "بیمار از درد قفسه سینه و تنگی نفس شکایت دارد. نوار قلب درخواست شد.",
                "specialty": "Cardiology",
                "mode": "ambient",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "درد قفسه سینه" in data["full_note"]
    assert data["report"]["chief_complaint"] == "درد قفسه سینه"
    assert isinstance(data["dictionary"], list)


def test_compose_full_note_skips_empty_sections():
    report = ClinicalReport(chief_complaint="سرفه", plan="۱. عکس قفسه سینه")
    note = compose_full_note(report)
    assert "شکایت اصلی" in note
    assert "برنامه" in note
    assert "معاینه" not in note


def test_specialty_label_persian():
    assert specialty_label("Cardiology") == "قلب و عروق"
    assert specialty_label("unknown") == "unknown"


def test_activate_downloaded_asr_writes_local_provider():
    from server.database.config.manager import config_manager

    updates = activate_downloaded_asr("whisper-large-v3-turbo-q6_k")
    assert updates["ASR_PROVIDER"] == "local"
    assert updates["ASR_MODEL"] == "whisper-large-v3-turbo-q6_k"
    config = config_manager.get_config()
    assert config["ASR_PROVIDER"] == "local"
    assert config["ASR_MODEL"] == "whisper-large-v3-turbo-q6_k"


def test_activate_downloaded_llm_writes_local_provider():
    from server.database.config.manager import config_manager

    updates = activate_downloaded_llm("qwen3.5-4b")
    assert updates["LLM_PROVIDER"] == "local"
    assert "Qwen3.5-4B" in updates["PRIMARY_MODEL"]
    config = config_manager.get_config()
    assert config["LLM_PROVIDER"] == "local"
