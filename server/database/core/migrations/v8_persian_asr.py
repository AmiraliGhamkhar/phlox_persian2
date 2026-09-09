"""Migration v8: Persian/mixed-language ASR defaults."""

import json

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
        "quick_chat_3_title": (
            "Other conditions worth reviewing",
            "بیماری‌های دیگری که ارزش بررسی دارند",
        ),
        "quick_chat_3_prompt": (
            "Other conditions worth reviewing",
            "بیماری‌های دیگری که ارزش بررسی دارند",
        ),
    }
    for key, (english_default, persian_default) in quick_chat_defaults.items():
        cursor.execute(
            f"UPDATE user_settings SET {key} = ? WHERE {key} = ?",
            (persian_default, english_default),
        )

    # (Letter-template localization removed: the simplified app has no letters.)

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
