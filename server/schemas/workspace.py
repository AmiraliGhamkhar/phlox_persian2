"""Schemas for the simplified specialty / transcription / report workspace."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClinicalReport(BaseModel):
    """Structured clinical note generated from a transcript."""

    model_config = ConfigDict(extra="forbid")

    chief_complaint: str = Field(
        default="",
        description="شکایت اصلی یا علت مراجعه در یک جمله کوتاه فارسی",
    )
    history: str = Field(
        default="",
        description="شرح‌حال مرتبط استخراج‌شده از متن؛ گلوله‌ای یا پاراگراف کوتاه",
    )
    examination: str = Field(
        default="",
        description="یافته‌های معاینه، علائم حیاتی و نتایج ذکرشده در متن",
    )
    assessment: str = Field(
        default="",
        description="برداشت بالینی مبتنی بر متن؛ بدون تشخیص قطعی ابداعی",
    )
    plan: str = Field(
        default="",
        description="برنامه اقدامات ذکرشده در متن، ترجیحاً شماره‌دار",
    )
    full_note: str = Field(
        default="",
        description="یادداشت کامل فارسی آماده کپی برای پرونده",
    )


class GenerateReportRequest(BaseModel):
    transcript: str = Field(..., min_length=1, description="متن پیاده‌سازی‌شده ویزیت")
    specialty: str | None = Field(default=None, description="تخصص پزشک")
    mode: Literal["ambient", "dictate"] = "ambient"
    clinician_name: str | None = None
    # ASR hygiene metadata from /dictate (segment confidence classes and
    # artifact flags). Forwarded into the report prompt so the model is told
    # which spans are uncertain instead of silently trusting them.
    transcript_flags: list[dict] = Field(default_factory=list)
    # Text of the low-confidence / suspect spans to be handled carefully.
    low_confidence_spans: list[str] = Field(default_factory=list)


class GenerateReportResponse(BaseModel):
    report: ClinicalReport
    full_note: str
    dictionary: list[dict] = Field(default_factory=list)
    process_duration: float = 0.0
    # Deterministic faithfulness warnings (number drift, unit mismatch,
    # negation flip, ungrounded terms, low-overlap sentences). The report is
    # always returned; warnings are review items for the clinician, never
    # blocking errors.
    warnings: list[dict] = Field(default_factory=list)


class DictionarySearchResponse(BaseModel):
    query: str
    matches: list[dict]
    total: int
