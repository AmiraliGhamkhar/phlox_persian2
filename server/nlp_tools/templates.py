import json
import logging
import re
import time
from datetime import datetime

from server.database.config.defaults.templates import DefaultTemplates
from server.database.config.manager import config_manager
from server.database.repositories.templates import template_exists
from server.llm_client import repair_json
from server.llm_client.client import get_llm_client
from server.schemas.templates import (
    ClinicalTemplate,
    ExtractedTemplate,
    FormatStyle,
    TemplateField,
)

# Set up module-level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def generate_template_from_note(example_note: str) -> ClinicalTemplate:
    """
    Analyzes an example note using LLM and generates a structured ClinicalTemplate.
    Extracts formatting patterns and appropriate section starters.
    """
    try:
        config = config_manager.get_config()
        options = config_manager.get_prompts_and_options()["options"]["general"]

        client = get_llm_client(timeout=300)
        _model_name = config["PRIMARY_MODEL"].lower()

        system_prompt = """
        تو متخصص مستندسازی پزشکی هستی و یادداشت‌های بالینی را تحلیل می‌کنی تا قالبی ساختاریافته بسازی. همه متن‌های توضیحی، نام بخش‌ها، نام پیشنهادی قالب و دستورهای تولید را به فارسی برگردان؛ نام داروها، اختصارات، شناسه‌ها و محتوای نمونه را دقیق حفظ کن.
        برای هر بخش:
        ۱. نوع قالب را تعیین کن (گلوله‌ای، شماره‌دار، روایی و مانند آن).
        ۲. الگوی دقیق گلوله‌گذاری یا شماره‌گذاری را پیدا کن (-، ۱.، •، *، # و مانند آن).
        ۳. آغازگر بخشی متناسب با قالب بساز و عنوان و نشانگر ابتدایی را در صورت وجود حفظ کن.
        ۴. متن بخش را از یادداشت نمونه، برای استفاده به‌عنوان نمونه سبک، استخراج کن.
        ۵. یک دستور سیستم مشخص و قابل اقدام برای تولید محتوای مشابه بساز.

        هر بخش باید این موارد را داشته باشد:
        - field_name: نام فارسی بخش
        - format_style: یکی از bullets، numbered، narrative، heading_with_bullets یا lab_values
        - bullet_type: مانند -، • یا *، در صورت استفاده از گلوله
        - section_starter: آغازگر بخش، مانند «شرح‌حال:\n-»
        - example_text: متن واقعی همان بخش از یادداشت
        - system_prompt: دستور فارسی مشخص برای تولید محتوای مشابه با همان سبک و لحن

        اگر بخشی مربوط به برنامه یا Plan است، نام آن را «برنامه» بگذار و format_style آن را numbered قرار بده. فقط JSON معتبر خروجی بده.
        """

        json_schema_instruction = (
            "فقط JSON معتبر با کلیدهای سطح بالا شامل "
            '\"sections\" (آرایه)، \"suggested_name\" (رشته) و \"note_type\" (رشته) برگردان. نمونه: '
            + json.dumps(
                {
                    "sections": [
                        {
                            "field_name": "شرح‌حال اصلی",
                            "format_style": "bullets",
                            "bullet_type": "-",
                            "section_starter": "شرح‌حال:\n-",
                            "example_text": "...",
                            "system_prompt": "شکایت اصلی و خط زمانی علائم را در نکات گلوله‌ای کوتاه ثبت کن و شروع، مدت، شدت، عوامل تشدیدکننده یا تسکین‌دهنده و علائم همراه را در صورت وجود بیاور.",
                            "persistent": False,
                            "required": False,
                        }
                    ],
                    "suggested_name": "قالب بالینی",
                    "note_type": "یادداشت بالینی",
                },
                ensure_ascii=False,
            )
        )

        base_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""این یادداشت بالینی را تحلیل کن و بخش‌های قالب را همراه با الگوهای قالب‌بندی آن استخراج کن.

{json_schema_instruction}

هیچ تب، فاصله اضافی، Markdown، کدبلاک یا نویسه قالب‌بندی اضافه نکن. پاسخ باید JSON فشرده و بدون قالب‌بندی زیبا باشد.

{example_note}""",
            },
        ]

        # Set up response format for structured output
        base_schema = ExtractedTemplate.model_json_schema()

        # Generate the template analysis with structured output
        response_json = await client.chat_with_structured_output(
            model=config["PRIMARY_MODEL"],
            messages=base_messages,
            schema=base_schema,
            options=options,
        )

        # Some endpoints ignore structured-output constraints and may wrap JSON in text/markdown.
        if isinstance(response_json, str):
            response_json = repair_json(response_json)
        else:
            response_json = json.dumps(response_json)

        extracted = ExtractedTemplate.model_validate_json(response_json)

        # Convert extracted sections to TemplateField objects
        template_fields = []

        # Add all extracted sections except plan
        for section in extracted.sections:
            field_key = generate_field_key(section.field_name)
            if not _is_plan_field(section.field_name):
                # Create format_schema based on format_style
                format_schema = None
                if section.format_style == FormatStyle.BULLETS:
                    format_schema = {
                        "type": "bullet",
                        "bullet_char": section.bullet_type or "-",
                    }
                elif section.format_style == FormatStyle.NUMBERED:
                    format_schema = {"type": "numbered"}
                elif section.format_style == FormatStyle.HEADING_WITH_BULLETS:
                    format_schema = {
                        "type": "heading_with_bullets",
                        "bullet_char": section.bullet_type or "-",
                    }

                field = TemplateField(
                    field_key=field_key,
                    field_name=section.field_name,
                    field_type="text",
                    required=section.required,
                    persistent=section.persistent,
                    system_prompt=section.system_prompt,
                    style_example=section.example_text,  # Use example text
                    format_schema=format_schema,
                    refinement_rules=["default"],  # Deprecated
                )
                template_fields.append(field)

        # Update plan field's style example
        plan_section = next(
            (s for s in extracted.sections if _is_plan_field(s.field_name)),
            None,
        )

        plan_field = DefaultTemplates.get_plan_field()
        if plan_section:
            # Extract the example text and ensure it's in numbered format
            plan_example = plan_section.example_text

            # Check if the example is already in a numbered format
            if not re.match(r"^\s*[\d۰-۹]+\.", plan_example.lstrip()):
                # Convert to numbered format if it's not already
                lines = [line.strip() for line in plan_example.split("\n") if line.strip()]
                plan_example = "\n".join(
                    f"{i + 1}. {line.lstrip('- •*').strip()}" for i, line in enumerate(lines)
                )

            plan_field["style_example"] = plan_example
            plan_field["format_schema"] = {"type": "numbered"}

        template_fields.append(TemplateField(**plan_field))

        # Generate a unique template key based on the suggested name
        new_template_key = generate_unique_template_key(extracted.suggested_name)

        template = ClinicalTemplate(
            template_key=new_template_key,
            template_name=extracted.suggested_name,
            fields=template_fields,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        return template

    except Exception as e:
        logging.error(f"Error generating template from note: {e}")
        raise


def generate_field_key(field_name: str) -> str:
    """Generate a standardized field key from a field name."""
    return field_name.lower().strip().replace(" ", "_")


def _is_plan_field(field_name: str) -> bool:
    """Recognize the plan section in both Persian and legacy English output."""
    return generate_field_key(field_name) in {"plan", "برنامه", "برنامه_مدیریت"}


def generate_unique_template_key(base_name: str) -> str:
    """
    Generate a unique template key based on the template name.
    If base name already exists (including soft-deleted), append -a, -b, -c etc.
    All template keys will have _1 appended as initial version.

    Args:
        base_name: The suggested template name to base the key on

    Returns:
        str: A unique template key with version number
    """
    base_key = generate_field_key(base_name)
    version = "_1"  # Initial version number

    # First try without any suffix - check both active and deleted templates
    # since UNIQUE constraint applies to all rows regardless of deleted status
    if not template_exists(f"{base_key}{version}", include_deleted=True):
        return f"{base_key}{version}"

    # If exists, try with suffixes -a through -z
    for suffix in (chr(i) for i in range(97, 123)):  # a through z
        test_key = f"{base_key}-{suffix}{version}"
        if not template_exists(test_key, include_deleted=True):
            return test_key

    # If we somehow run out of letters, add timestamp
    return f"{base_key}-{int(time.time())}{version}"
