"""Migration v8: Persian/mixed-language ASR defaults."""

import json

from server.database.config.defaults.letters import DefaultLetters
from server.database.config.defaults.prompts import DEFAULT_PROMPTS


def migrate(cursor, _db):
    """Add the ASR language preference without overwriting existing settings."""
    # ``auto`` is the safest default for Persian-only and mixed Persian/English
    # recordings. Existing WHISPER_* keys remain supported for compatibility.
    cursor.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("ASR_LANGUAGE", json.dumps("auto")),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("ASR_PROVIDER", json.dumps("openai_compatible")),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("WHISPER_LANGUAGE", json.dumps("auto")),
    )
    for key in ("ASR_BASE_URL", "ASR_MODEL", "ASR_KEY"):
        cursor.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
            (key, json.dumps("")),
        )
    for canonical_key, legacy_key in (
        ("ASR_BASE_URL", "WHISPER_BASE_URL"),
        ("ASR_MODEL", "WHISPER_MODEL"),
        ("ASR_KEY", "WHISPER_KEY"),
    ):
        cursor.execute(
            """
            UPDATE config
            SET value = (SELECT value FROM config WHERE key = ?)
            WHERE key = ? AND value = ?
            """,
            (legacy_key, canonical_key, json.dumps("")),
        )

    # Localize only the original untouched quick-chat defaults. A clinician's
    # custom wording is preserved.
    quick_chat_defaults = {
        "quick_chat_1_title": ("Review my plan", "بررسی برنامه من"),
        "quick_chat_1_prompt": ("Review my plan", "بررسی برنامه من"),
        "quick_chat_2_title": ("Additional points to review", "نکات دیگری برای بررسی"),
        "quick_chat_2_prompt": ("Additional points to review", "نکات دیگری برای بررسی"),
        "quick_chat_3_title": ("Other conditions worth reviewing", "بیماری‌های دیگری که ارزش بررسی دارند"),
        "quick_chat_3_prompt": ("Other conditions worth reviewing", "بیماری‌های دیگری که ارزش بررسی دارند"),
    }
    for key, (english_default, persian_default) in quick_chat_defaults.items():
        cursor.execute(
            f"UPDATE user_settings SET {key} = ? WHERE {key} = ?",
            (persian_default, english_default),
        )

    # Migrate the original built-in letter names and instructions only when
    # they are still untouched. Custom clinician templates are preserved.
    original_letters = [
        (
            "GP Letter",
            "Write a brief letter to the patient's general practitioner...",
        ),
        ("Specialist Referral", "Write a detailed referral letter..."),
        ("Discharge Summary", "Write a comprehensive discharge summary..."),
        ("Brief Update", "Write a short update letter..."),
    ]
    for (_, persian_name, persian_instructions), (original_name, original_instructions) in zip(
        DefaultLetters.get_default_letter_templates(), original_letters
    ):
        cursor.execute(
            """
            UPDATE letter_templates
            SET name = ?, instructions = ?
            WHERE name = ? AND instructions = ?
            """,
            (persian_name, persian_instructions, original_name, original_instructions),
        )

    dictation_name, dictation_instructions = DefaultLetters.get_dictation_template()
    original_dictation_instructions = (
        "I'm going to dictate a letter to you. Please adjust the punctuation "
        "and wording where required to make it a polished letter; the substance, "
        "overall structure MUST remain as dictated. Even the wording should be "
        "largely the same. You are not to rephrase the letter in any substantial way.\n\n"
        "IMPORTANT: Please adhere to any instructions that may appear in the transcript; "
        "for example 'remove that' or 'insert a summary of the patients blood results'. "
        "Execute these instructions instead of transcribing them."
    )
    cursor.execute(
        """
        UPDATE letter_templates
        SET name = ?, instructions = ?
        WHERE name = ? AND instructions = ?
        """,
        (dictation_name, dictation_instructions, "Dictation", original_dictation_instructions),
    )

    # Localize untouched built-in prompts while preserving edits made in the
    # settings screen. The prefix checks distinguish the original defaults
    # from arbitrary clinician-authored instructions.
    prompt_defaults = {
        "refinement": "You are an editing assistant.",
        "chat": "You are a helpful documentation and informational assistant",
        "summary": "Summarize the patient's condition",
        "letter": "You are a professional medical correspondence writer.",
        "reasoning": "You are a concise educational chart-review assistant.",
        "job_extraction": "You are a clinical task extractor.",
    }
    for key, original_prefix in prompt_defaults.items():
        cursor.execute("SELECT system FROM prompts WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row and (row["system"] or "").startswith(original_prefix):
            cursor.execute(
                "UPDATE prompts SET system = ? WHERE key = ?",
                (DEFAULT_PROMPTS["prompts"][key]["system"], key),
            )
