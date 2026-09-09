"""Every prompt key in DEFAULT_PROMPTS['prompts'] must be documented.

The registry (server/nlp_tools/prompt_registry.py) records the status and
intended user of each stored prompt key. A new key added to
DEFAULT_PROMPTS['prompts'] without a registry entry fails here, which stops
unreviewed prompts from entering the system silently.
"""

from server.database.config.defaults.prompts import DEFAULT_PROMPTS
from server.nlp_tools.prompt_registry import PROMPT_REGISTRY


def test_registry_covers_all_prompt_keys():
    assert set(DEFAULT_PROMPTS["prompts"].keys()) == set(PROMPT_REGISTRY.keys())


def test_registry_entries_are_documented():
    for key, entry in PROMPT_REGISTRY.items():
        assert entry.get("status"), f"{key}: status required"
        assert entry.get("used_by"), f"{key}: used_by required"
        assert entry.get("review"), f"{key}: review required"


def test_live_report_path_does_not_use_db_report_key():
    """The workspace report path builds from REPORT_SYSTEM_PROMPT, not the
    'report' prompt key — the registry must say so."""
    assert PROMPT_REGISTRY["report"]["status"] == "unused"
    from server.nlp_tools import report as report_module

    assert hasattr(report_module, "REPORT_SYSTEM_PROMPT")
    # The live system prompt must carry the safety rules, independent of the
    # stored 'report' key text.
    assert "قواعد ایمنی مستندسازی" in report_module.REPORT_SYSTEM_PROMPT
