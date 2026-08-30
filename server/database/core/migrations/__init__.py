"""Migration package — per-version files with a central registry."""

from server.database.core.migrations import (
    v1_initial_schema,
    v2_reasoning,
    v3_config_openai,
    v4_user_settings_and_cleanup,
    v5_mcp_servers,
    v6_patient_profiles,
    v7_audit_log,
    v8_persian_asr,
    v9_mcp_tool_toggles,
    v10_ai_providers,
)
from server.database.core.migrations.runner import run_migrations

MIGRATIONS = {
    1: v1_initial_schema.migrate,
    2: v2_reasoning.migrate,
    3: v3_config_openai.migrate,
    4: v4_user_settings_and_cleanup.migrate,
    5: v5_mcp_servers.migrate,
    6: v6_patient_profiles.migrate,
    7: v7_audit_log.migrate,
    8: v8_persian_asr.migrate,
    9: v9_mcp_tool_toggles.migrate,
    10: v10_ai_providers.migrate,
}

__all__ = ["run_migrations", "MIGRATIONS"]
