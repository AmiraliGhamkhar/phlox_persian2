"""Simplified clinician workspace: specialty, dictionary, and report generation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from server.data.medical_dictionary import load_terms, search
from server.database.config.manager import config_manager
from server.nlp_tools.report import generate_clinical_report
from server.nlp_tools.specialties import SPECIALTIES
from server.schemas.workspace import GenerateReportRequest, GenerateReportResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _llm_ready(config: dict) -> bool:
    provider = (config.get("LLM_PROVIDER") or "").strip()
    model = (config.get("PRIMARY_MODEL") or "").strip()
    if provider == "local":
        return True
    if provider in {"openai", "anthropic", "fireworks", "groq", "openrouter"}:
        return bool((config.get("LLM_API_KEY") or "").strip())
    return bool(model or (config.get("LLM_BASE_URL") or "").strip())


def _asr_ready(config: dict) -> bool:
    provider = (config.get("ASR_PROVIDER") or config.get("LLM_PROVIDER") or "").strip()
    if provider == "local":
        return True
    key = (config.get("ASR_KEY") or config.get("WHISPER_KEY") or "").strip()
    batch_key = (config.get("ASR_BATCH_KEY") or config.get("WHISPER_BATCH_KEY") or "").strip()
    if provider in {"speechmatics", "assemblyai", "fireworks"}:
        return bool(key or batch_key)
    if provider == "openai":
        return bool(key)
    # openai_compatible / whispercpp / custom: a leftover local model id must
    # not mark the workspace ready when no ASR endpoint is configured.
    return bool((config.get("ASR_BASE_URL") or config.get("WHISPER_BASE_URL") or "").strip())


@router.get("/specialties")
def list_specialties():
    """Return the specialty cards for the first page."""
    return {"specialties": SPECIALTIES}


@router.get("/status")
def workspace_status():
    """Tell the UI whether speech and report generation are ready."""
    config = config_manager.get_config()
    user = config_manager.get_user_settings() or {}
    return {
        "specialty": user.get("specialty") or "",
        "name": user.get("name") or "",
        "llm_ready": _llm_ready(config),
        "asr_ready": _asr_ready(config),
        "llm_provider": config.get("LLM_PROVIDER") or "",
        "asr_provider": config.get("ASR_PROVIDER") or "",
        "primary_model": config.get("PRIMARY_MODEL") or "",
        "asr_model": config.get("ASR_MODEL") or config.get("WHISPER_MODEL") or "",
        "asr_language": config.get("ASR_LANGUAGE") or config.get("WHISPER_LANGUAGE") or "auto",
    }


@router.get("/dictionary")
def search_dictionary(
    q: str = Query("", description="Persian or English medical term"),
    limit: int = Query(20, ge=1, le=50),
):
    """Bilingual medical dictionary lookup for the workspace page."""
    query = (q or "").strip()
    if not query:
        _fa, _en, entries = load_terms()
        preview = [
            {"fa": item["fa"], "en": item["en"], "cat": item["cat"]} for item in entries[:limit]
        ]
        return {"query": "", "matches": preview, "total": len(entries)}
    matches = search(query, limit=limit, threshold=50)
    return {"query": query, "matches": matches, "total": len(matches)}


@router.post("/report", response_model=GenerateReportResponse)
async def generate_report(payload: GenerateReportRequest):
    """Turn a transcript into a specialty-aware clinical note."""
    transcript = (payload.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="متن پیاده‌سازی‌شده خالی است.")
    try:
        result = await generate_clinical_report(
            transcript=transcript,
            specialty=payload.specialty,
            mode=payload.mode,
            clinician_name=payload.clinician_name,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.error("Workspace report failed: %s", error)
        raise HTTPException(
            status_code=500,
            detail="تولید گزارش ناموفق بود. اتصال مدل زبانی را در تنظیمات بررسی کنید.",
        ) from error
    return GenerateReportResponse(
        report=result["report"],
        full_note=result["full_note"],
        dictionary=result["dictionary"],
        process_duration=result["process_duration"],
    )
