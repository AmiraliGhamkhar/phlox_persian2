"""Specialty-aware clinical report generation from a transcript.

This is the only LLM path used by the simplified three-page app. It does not
require a patient record. The system prompt is medical, Persian-first, and
grounded in the bundled Persian⇄English dictionary.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from server.data.medical_dictionary import terminology_reference_block, terms_for_context
from server.database.config.manager import config_manager
from server.llm_client import repair_json
from server.llm_client.client import get_llm_client
from server.schemas.workspace import ClinicalReport
from server.transcription.hygiene import deterministic_options

logger = logging.getLogger(__name__)

SPECIALTY_FOCUS: dict[str, str] = {
    "anaesthetics": "روی ارزیابی پیش از بیهوشی، راه هوایی، وضعیت قلبی‌ریوی، داروهای مصرفی و برنامه بیهوشی تمرکز کن.",
    "cardiology": "روی درد قفسه سینه، تنگی نفس، تپش قلب، ادم، ریتم، فشار خون، داروهای قلبی و بررسی‌های قلبی تمرکز کن.",
    "dermatology": "روی ضایعات پوستی، محل، شکل، خارش، مدت، درمان‌های قبلی و تشخیص افتراقی پوستی تمرکز کن.",
    "emergency medicine": "روی شکایت حاد، ثبات همودینامیک، علائم خطر، اقدامات فوری و برنامه اورژانس تمرکز کن.",
    "endocrinology": "روی دیابت، تیروئید، وزن، قند خون، HbA1c، داروهای غدد و عوارض تمرکز کن.",
    "family medicine": "روی مراقبت جامع، بیماری‌های مزمن، پیشگیری، داروها و پیگیری خانوادگی تمرکز کن.",
    "gastroenterology": "روی درد شکم، تهوع، خونریزی گوارشی، اجابت مزاج، کبد و آندوسکوپی تمرکز کن.",
    "general practice": "روی مراقبت اولیه، شکایت اصلی، بیماری‌های شایع، داروها و ارجاع در صورت نیاز تمرکز کن.",
    "general surgery": "روی اندیکاسیون جراحی، معاینه شکم، زخم، عوارض و برنامه پیش/پس از عمل تمرکز کن.",
    "geriatrics": "روی چنددارویی، سقوط، شناخت، عملکرد روزانه و اهداف مراقبت سالمندی تمرکز کن.",
    "haematology": "روی شمارش خون، خونریزی، لخته، طحال، درمان‌های خونی و نتایج آزمایش تمرکز کن.",
    "internal medicine": "روی شرح‌حال دستگاهی، بیماری‌های مزمن، داروها، آزمایش‌ها و برنامه داخلی تمرکز کن.",
    "neurology": "روی سردرد، ضعف، تشنج، شناخت، معاینه عصبی و تصویربرداری مغز و اعصاب تمرکز کن.",
    "obstetrics and gynaecology": "روی بارداری، سیکل، خونریزی، درد لگنی، معاینه و برنامه زنان و زایمان تمرکز کن.",
    "oncology": "روی نوع سرطان، مرحله، درمان‌های قبلی، سمیت درمان و برنامه انکولوژی تمرکز کن.",
    "ophthalmology": "روی کاهش دید، درد چشم، قرمزی، فشار داخل چشم و معاینه چشم تمرکز کن.",
    "orthopaedics": "روی درد اسکلتی، تروما، محدودیت حرکت، تصویربرداری و برنامه ارتوپدی تمرکز کن.",
    "paediatrics": "روی سن کودک، رشد، تب، تغذیه، واکسیناسیون و نگرانی والدین تمرکز کن.",
    "psychiatry": "روی خلق، اضطراب، خواب، افکار خودکشی، داروها و وضعیت روانی تمرکز کن.",
    "radiology": "روی اندیکاسیون تصویربرداری، یافته‌های کلیدی و توصیه تصویربرداری تمرکز کن.",
    "respiratory medicine": "روی سرفه، تنگی نفس، خس‌خس، اشباع اکسیژن، اسپیرومتری و تصویر قفسه سینه تمرکز کن.",
    "rheumatology": "روی درد مفاصل، خشکی صبحگاهی، تورم، آزمایش‌های خودایمنی و برنامه روماتولوژی تمرکز کن.",
    "urology": "روی ادرار، هماچوری، پروستات، سنگ و عفونت ادراری تمرکز کن.",
}

REPORT_SYSTEM_PROMPT = """تو منشی مستندسازی بالینی برای پزشک متخصص هستی، نه ابزار تشخیص و نه تصمیم‌گیرنده درمانی.

وظیفه:
از متن پیاده‌سازی‌شده ویزیت، یک یادداشت بالینی ساختاریافته و حرفه‌ای به فارسی بنویس.

قواعد ایمنی مستندسازی (اجباری):
- فقط آنچه در متن گفته شده را بنویس. واقعیت، دارو، دوز، آزمایش یا برنامه اختراع نکن.
- اعداد، واحدها، نام داروها، مخفف‌ها و شناسه‌ها را دقیقاً حفظ کن.
- نفی و تردید را حفظ کن («درد قفسه سینه ندارد» هرگز به «درد قفسه سینه» تبدیل نشود).
- اگر بخشی در متن نیست، همان بخش را خالی بگذار؛ حدس نزن.
- تشخیص قطعی یا توصیه درمانی خارج از متن ارائه نده.
- اصطلاحات پزشکی انگلیسی رایج و نام داروها را ترجمه یا آوانویسی نکن.
- اگر بخشی از متن مبهم، نامفهم یا ناقص است (احتمال خطای پیاده‌سازی صوتی)، همان عبارت را دقیقاً عیناً بنویس و با «نامشخص» نشانه‌گذاری کن؛ هرگز عدد، دوز، واحد یا یافته مبهم را حدس نزن، اصلاح نکن یا کامل مکن. اگر آن بخش قابل اعتماد نیست، بهتر است حذف شود تا اشتباه ثبت شود.
- خروجی فقط JSON معتبر با کلیدهای chief_complaint، history، examination، assessment، plan، full_note باشد.
- full_note باید یادداشت کامل فارسی آماده کپی باشد و بخش‌های خالی را حذف کند.

حالت کاری:
{mode_instruction}

تخصص پزشک: {specialty_label}
تمرکز تخصصی: {specialty_focus}

{dictionary_block}
"""


def _specialty_key(specialty: str | None) -> str:
    return (specialty or "").strip().lower()


def specialty_label(specialty: str | None) -> str:
    from server.nlp_tools.specialties import SPECIALTY_BY_KEY

    key = _specialty_key(specialty)
    info = SPECIALTY_BY_KEY.get(key)
    if info:
        return info["fa"]
    return specialty or "پزشکی عمومی"


_MAX_SPANS_IN_PROMPT = 8
_MAX_SPAN_CHARS = 160


def _low_confidence_block(spans: list[str] | None) -> str:
    """Persian instruction block for ASR-flagged spans (empty when none)."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in spans or []:
        span = str(raw or "").strip()[:_MAX_SPAN_CHARS]
        if not span or span in seen:
            continue
        seen.add(span)
        cleaned.append(span)
        if len(cleaned) >= _MAX_SPANS_IN_PROMPT:
            break
    if not cleaned:
        return ""
    lines = "\n".join(f"- «{span}»" for span in cleaned)
    return (
        "\nقطعات کم‌اعتمادی پیاده‌سازی (موتور ASR این بخش‌ها را نامطمئن یا آلوده به خطا علامت‌گذاری کرد):\n"
        f"{lines}\n"
        "محتوای این قطعات را به‌عنوان حقیقت برقرارشده در یادداشت بیان نکن. "
        "اگر لازم است، دقیقاً عیناً (و با نشانه «نامشخص») بنویس؛ در غیر این صورت حذف کن.\n"
    )


def build_report_system_prompt(
    *,
    specialty: str | None,
    mode: str,
    transcript: str,
    clinician_name: str | None = None,
    low_confidence_spans: list[str] | None = None,
) -> str:
    key = _specialty_key(specialty)
    focus = SPECIALTY_FOCUS.get(key, "روی شکایت اصلی، شرح‌حال، یافته‌ها و برنامه ذکرشده تمرکز کن.")
    if mode == "dictate":
        mode_instruction = (
            "پزشک یادداشت را دیکته کرده است. متن را به یادداشت رسمی، منظم و بدون تکرار تبدیل کن؛ "
            "محتوا را گسترش نده."
        )
    else:
        mode_instruction = "متن مکالمه محیطی پزشک و بیمار است. نکات بالینی مرتبط را استخراج و در بخش‌های یادداشت سازمان بده."
    dictionary_block = terminology_reference_block(transcript, max_terms=50)
    prompt = REPORT_SYSTEM_PROMPT.format(
        mode_instruction=mode_instruction,
        specialty_label=specialty_label(specialty),
        specialty_focus=focus,
        dictionary_block=dictionary_block or "",
    )
    if clinician_name:
        prompt += f"\nنام پزشک: {clinician_name}\n"
    prompt += _low_confidence_block(low_confidence_spans)
    return prompt


def compose_full_note(report: ClinicalReport) -> str:
    """Build a copy-ready Persian note from structured sections."""
    if (report.full_note or "").strip():
        return report.full_note.strip()
    parts: list[str] = []
    mapping = [
        ("شکایت اصلی", report.chief_complaint),
        ("شرح‌حال", report.history),
        ("معاینه و یافته‌ها", report.examination),
        ("ارزیابی", report.assessment),
        ("برنامه", report.plan),
    ]
    for title, body in mapping:
        text = (body or "").strip()
        if text:
            parts.append(f"{title}:\n{text}")
    return "\n\n".join(parts)


async def generate_clinical_report(
    transcript: str,
    specialty: str | None = None,
    mode: str = "ambient",
    clinician_name: str | None = None,
    transcript_flags: list[dict] | None = None,
    low_confidence_spans: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a structured clinical report from a transcript.

    After generation, the note is checked against the source transcript with
    deterministic faithfulness guards (see ``server.nlp_tools.verification``).
    Findings are returned as ``warnings`` — review items for the clinician,
    never blocking: the note is always returned.
    """
    started = time.perf_counter()
    transcript_text = (transcript or "").strip()
    if not transcript_text:
        empty = ClinicalReport()
        return {
            "report": empty,
            "full_note": "",
            "dictionary": [],
            "process_duration": 0.0,
            "warnings": [],
        }

    config = config_manager.get_config()
    model_name = (config.get("PRIMARY_MODEL") or "").strip()
    if not model_name and config.get("LLM_PROVIDER") != "local":
        raise ValueError(
            "مدل زبانی تنظیم نشده است. ابتدا در تنظیمات یک ارائه‌دهنده یا مدل محلی را آماده کنید."
        )

    user = config_manager.get_user_settings() or {}
    specialty = specialty or user.get("specialty") or ""
    clinician_name = clinician_name or user.get("name") or None

    options = deterministic_options(
        config_manager.get_prompts_and_options()["options"].get("general", {})
    )
    spans = _spans_from_flags(low_confidence_spans, transcript_flags)
    system_content = build_report_system_prompt(
        specialty=specialty,
        mode=mode,
        transcript=transcript_text,
        clinician_name=clinician_name,
        low_confidence_spans=spans,
    )
    client = get_llm_client()
    response_format = ClinicalReport.model_json_schema()
    messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": (
                f"<clinical_transcript_data>\n{transcript_text}\n</clinical_transcript_data>"
            ),
        },
    ]
    try:
        response = await client.chat(
            model=model_name or "local",
            messages=messages,
            format=response_format,
            options=options,
        )
        content = response["message"]["content"] if isinstance(response, dict) else ""
        repaired = repair_json(str(content or ""))
        report = ClinicalReport.model_validate_json(repaired)
    except Exception as error:
        logger.error("Clinical report generation failed: %s", error)
        raise

    full_note = compose_full_note(report)
    if full_note and not report.full_note:
        report = report.model_copy(update={"full_note": full_note})
    dictionary = terms_for_context(transcript_text, max_terms=40)
    return {
        "report": report,
        "full_note": full_note,
        "dictionary": dictionary,
        "process_duration": float(f"{time.perf_counter() - started:.2f}"),
        "warnings": _verify_full_note(transcript_text, full_note),
    }


def _spans_from_flags(
    explicit_spans: list[str] | None,
    transcript_flags: list[dict] | None,
) -> list[str]:
    """Prefer caller-provided spans; otherwise derive them from ASR flags."""
    spans = [str(s).strip() for s in (explicit_spans or []) if str(s or "").strip()]
    if spans:
        return spans
    for flag in transcript_flags or []:
        if not isinstance(flag, dict):
            continue
        text = str(flag.get("text") or "").strip()
        if text:
            spans.append(text)
    return spans


def _verify_full_note(transcript_text: str, full_note: str) -> list[dict[str, str]]:
    """Deterministic faithfulness check; any failure degrades to no warnings."""
    if not full_note:
        return []
    try:
        from server.nlp_tools.verification import verify_note

        return verify_note(transcript_text, full_note).warnings()
    except Exception:  # noqa: BLE001 — verification must never break the report
        logger.warning("Note verification failed; returning report without warnings", exc_info=True)
        return []
