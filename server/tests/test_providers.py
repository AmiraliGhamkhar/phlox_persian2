"""Tests for the LLM / ASR / embedding provider catalog."""

from server.utils.providers import (
    apply_asr_provider_defaults,
    apply_llm_provider_defaults,
    detect_llm_provider,
    list_providers,
    looks_like_embedding_model,
    normalize_provider_id,
    resolve_asr_connection,
    resolve_embedding_connection,
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
    embedding_ids = {item["id"] for item in catalog["embedding"]}
    assert {"ollama", "lmstudio", "llamacpp", "ninerouter", "omniroute", "openai", "anthropic"}.issubset(
        llm_ids
    )
    assert {"fireworks", "speechmatics", "whispercpp", "openai"}.issubset(asr_ids)
    assert {"ollama", "openai", "local"}.issubset(embedding_ids)


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
    assert detect_llm_provider({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "http://127.0.0.1:1234"}) == "lmstudio"
    assert detect_llm_provider({"LLM_PROVIDER": "openai", "LLM_BASE_URL": "https://api.openai.com"}) == "openai"
    assert detect_llm_provider({"LLM_PROVIDER": "openai", "LLM_BASE_URL": ""}) == "ollama"


def test_apply_provider_defaults_stamp_urls():
    llm = apply_llm_provider_defaults("lmstudio")
    assert llm["LLM_PROVIDER"] == "lmstudio"
    assert llm["LLM_BASE_URL"].endswith("1234")
    asr = apply_asr_provider_defaults("fireworks")
    assert asr["ASR_PROVIDER"] == "fireworks"
    assert asr["ASR_MODEL"] == "fireworks-asr-v2"


def test_embedding_provider_is_independent_of_llm():
    connection = resolve_embedding_connection(
        {
            "LLM_PROVIDER": "anthropic",
            "EMBEDDING_PROVIDER": "ollama",
            "EMBEDDING_MODEL": "nomic-embed-text",
        }
    )
    assert connection["provider"] == "ollama"
    assert "11434" in connection["base_url"]
    assert connection["model"] == "nomic-embed-text"


def test_asr_fireworks_and_speechmatics_support_live():
    fireworks = resolve_asr_connection({"ASR_PROVIDER": "fireworks", "ASR_KEY": "fw"})
    assert fireworks["supports_live"] is True
    assert fireworks["protocol"] == "fireworks"
    speechmatics = resolve_asr_connection({"ASR_PROVIDER": "speechmatics", "ASR_KEY": "sm"})
    assert speechmatics["protocol"] == "speechmatics"


def test_anthropic_llm_does_not_reuse_anthropic_for_embeddings():
    connection = resolve_embedding_connection(
        {
            "LLM_PROVIDER": "anthropic",
            "LLM_BASE_URL": "https://api.anthropic.com",
            "EMBEDDING_PROVIDER": "",
        }
    )
    assert connection["provider"] == "ollama"
    assert "11434" in connection["base_url"]


def test_looks_like_embedding_model():
    assert looks_like_embedding_model("text-embedding-3-small")
    assert looks_like_embedding_model("nomic-embed-text")
    assert not looks_like_embedding_model("gpt-4o")
