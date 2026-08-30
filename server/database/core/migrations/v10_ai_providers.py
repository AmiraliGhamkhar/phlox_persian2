"""Migration v10: named LLM / ASR / embedding providers."""

import json


def migrate(cursor, _db):
    """Add embedding-provider keys without overwriting existing settings."""
    defaults = {
        "EMBEDDING_PROVIDER": "",
        "EMBEDDING_BASE_URL": "",
        "EMBEDDING_API_KEY": "",
    }
    for key, value in defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )

    # If the user already has a named LLM provider, leave it. Otherwise keep
    # the historical empty-URL → Ollama behaviour by recording ollama when
    # LLM_PROVIDER is still the generic openai value with no cloud URL.
    cursor.execute("SELECT value FROM config WHERE key = 'LLM_PROVIDER'")
    row = cursor.fetchone()
    cursor.execute("SELECT value FROM config WHERE key = 'LLM_BASE_URL'")
    url_row = cursor.fetchone()
    provider = json.loads(row["value"]) if row else "openai"
    base_url = json.loads(url_row["value"]) if url_row else ""
    if provider in {"openai", "openai_compatible"} and not str(base_url or "").strip():
        cursor.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("LLM_PROVIDER", json.dumps("ollama")),
        )
