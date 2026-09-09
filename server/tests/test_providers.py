"""Tests for the LLM / ASR provider catalog."""

from server.utils.providers import (
    apply_asr_provider_defaults,
    apply_llm_provider_defaults,
    detect_llm_provider,
    list_providers,
    normalize_provider_id,
    resolve_asr_connection,
    resolve_llm_connection,
)


def test_normalize_provider_aliases():
    assert normalize_provider_id("9router", "llm") == "ninerouter"
    assert normalize_provider_id("lm-studio", "llm") == "lmstudio"
    assert normalize_provider_id("whisper.cpp", "asr") == "whispercpp"
    assert normalize_provider_id("openai-compatible", "llm") == "openai_compatible"


def test_list_providers_covers_requested_backends():
    catalog = list_providers()
    llm_ids = {item["id"] for item in catalog["llm"]}
    asr_ids = {item["id"] for item in catalog["asr"]}
    assert {
        "ollama",
        "lmstudio",
        "llamacpp",
        "ninerouter",
        "omniroute",
        "openai",
        "anthropic",
        "groq",
        "openrouter",
    }.issubset(llm_ids)
    assert {"fireworks", "speechmatics", "whispercpp", "openai"}.issubset(asr_ids)


def test_empty_openai_url_resolves_to_ollama():
    connection = resolve_llm_connection({"LLM_PROVIDER": "openai", "LLM_BASE_URL": ""})
    assert connection["provider"] == "ollama"
    assert "11434" in connection["base_url"]
    assert connection["protocol"] == "openai_compatible"


def test_anthropic_uses_messages_protocol():
    connection = resolve_llm_connection(
        {
            "LLM_PROVIDER": "anthropic",
            "LLM_BASE_URL": "",
            "LLM_API_KEY": "sk-ant-test",
        }
    )
    assert connection["protocol"] == "anthropic"
    assert "api.anthropic.com" in connection["base_url"]


def test_detect_llm_provider_from_url():
    assert (
        detect_llm_provider({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "http://127.0.0.1:1234"})
        == "lmstudio"
    )
    assert (
        detect_llm_provider({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "https://api.openai.com"})
        == "openai"
    )
    assert detect_llm_provider({"LLM_PROVIDER": "openai", "LLM_BASE_URL": ""}) == "ollama"
    assert (
        detect_llm_provider(
            {"LLM_PROVIDER": "openai_compatible", "LLM_BASE_URL": "https://api.groq.com/openai"}
        )
        == "groq"
    )
    assert (
        detect_llm_provider(
            {"LLM_PROVIDER": "openai_compatible", "LLM_BASE_URL": "https://openrouter.ai/api"}
        )
        == "openrouter"
    )


def test_apply_provider_defaults_stamp_urls():
    llm = apply_llm_provider_defaults("lmstudio")
    assert llm["LLM_PROVIDER"] == "lmstudio"
    assert llm["LLM_BASE_URL"].endswith("1234")
    groq = apply_llm_provider_defaults("groq")
    assert groq["LLM_PROVIDER"] == "groq"
    assert "api.groq.com" in groq["LLM_BASE_URL"]
    openrouter = apply_llm_provider_defaults("openrouter")
    assert openrouter["LLM_PROVIDER"] == "openrouter"
    assert "openrouter.ai" in openrouter["LLM_BASE_URL"]
    asr = apply_asr_provider_defaults("fireworks")
    assert asr["ASR_PROVIDER"] == "fireworks"
    assert asr["ASR_MODEL"] == "fireworks-asr-v2"


def test_asr_fireworks_and_speechmatics_support_live():
    fireworks = resolve_asr_connection({"ASR_PROVIDER": "fireworks", "ASR_KEY": "fw"})
    assert fireworks["supports_live"] is True
    assert fireworks["protocol"] == "fireworks"
    speechmatics = resolve_asr_connection({"ASR_PROVIDER": "speechmatics", "ASR_KEY": "sm"})
    assert speechmatics["protocol"] == "speechmatics"


def test_groq_and_openrouter_are_openai_compatible():
    groq = resolve_llm_connection(
        {"LLM_PROVIDER": "groq", "LLM_API_KEY": "gsk-test", "LLM_BASE_URL": ""}
    )
    assert groq["protocol"] == "openai_compatible"
    assert "api.groq.com" in groq["base_url"]
    openrouter = resolve_llm_connection(
        {"LLM_PROVIDER": "openrouter", "LLM_API_KEY": "sk-or-test", "LLM_BASE_URL": ""}
    )
    assert openrouter["protocol"] == "openai_compatible"
    assert "openrouter.ai" in openrouter["base_url"]
