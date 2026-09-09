/** Frontend catalog fallbacks matching server/utils/providers.py. */

export const LLM_PROVIDER_DEFAULTS = {
  local: { url: "", requiresKey: false, models: [] },
  ollama: { url: "http://127.0.0.1:11434", requiresKey: false, models: [] },
  lmstudio: { url: "http://127.0.0.1:1234", requiresKey: false, models: [] },
  llamacpp: { url: "http://127.0.0.1:8080", requiresKey: false, models: [] },
  ninerouter: { url: "http://127.0.0.1:20128", requiresKey: false, models: [] },
  omniroute: { url: "http://127.0.0.1:20128", requiresKey: false, models: [] },
  openai: {
    url: "https://api.openai.com",
    requiresKey: true,
    models: ["gpt-4.1", "gpt-4o", "gpt-4o-mini", "o4-mini"],
  },
  anthropic: {
    url: "https://api.anthropic.com",
    requiresKey: true,
    models: [
      "claude-sonnet-4-5",
      "claude-opus-4-1",
      "claude-haiku-4-5",
      "claude-3-5-sonnet-latest",
      "claude-3-5-haiku-latest",
    ],
  },
  fireworks: {
    url: "https://api.fireworks.ai/inference",
    requiresKey: true,
    models: [
      "accounts/fireworks/models/llama-v3p3-70b-instruct",
      "accounts/fireworks/models/qwen2p5-72b-instruct",
    ],
  },
  groq: {
    url: "https://api.groq.com/openai",
    requiresKey: true,
    models: [
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "openai/gpt-oss-120b",
      "moonshotai/kimi-k2-instruct",
    ],
  },
  openrouter: {
    url: "https://openrouter.ai/api",
    requiresKey: true,
    models: [
      "openai/gpt-4o-mini",
      "openai/gpt-4o",
      "anthropic/claude-sonnet-4",
      "google/gemini-2.0-flash-001",
    ],
  },
  openai_compatible: { url: "", requiresKey: false, models: [] },
};

export const ASR_PROVIDER_DEFAULTS = {
  local: { url: "", models: [], requiresKey: false },
  openai_compatible: { url: "", models: ["whisper-1"], requiresKey: false },
  openai: {
    url: "https://api.openai.com",
    models: ["gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"],
    requiresKey: true,
  },
  whispercpp: { url: "http://127.0.0.1:2022", models: ["whisper-1"], requiresKey: false },
  speechmatics: {
    url: "wss://global.rt.speechmatics.com/v2",
    batchUrl: "https://eu1.asr.api.speechmatics.com/v2",
    models: ["enhanced", "standard", "melia-1"],
    requiresKey: true,
  },
  assemblyai: {
    url: "https://api.assemblyai.com",
    models: ["universal-3-5-pro", "universal-2"],
    requiresKey: true,
  },
  fireworks: {
    url: "https://audio-prod.api.fireworks.ai",
    models: ["fireworks-asr-v2", "fireworks-asr-large", "whisper-v3-turbo", "whisper-v3"],
    requiresKey: true,
  },
};

export const applyLlmProviderDefaults = (providerId, handleConfigChange) => {
  const defaults = LLM_PROVIDER_DEFAULTS[providerId] || LLM_PROVIDER_DEFAULTS.openai_compatible;
  handleConfigChange("LLM_PROVIDER", providerId);
  if (providerId !== "openai_compatible") {
    handleConfigChange("LLM_BASE_URL", defaults.url);
  }
  const model = defaults.models?.[0] || "";
  if (model) {
    handleConfigChange("PRIMARY_MODEL", model);
    handleConfigChange("SECONDARY_MODEL", model);
    handleConfigChange("REASONING_MODEL", model);
  }
};

export const applyAsrProviderDefaults = (providerId, handleConfigChange) => {
  const defaults = ASR_PROVIDER_DEFAULTS[providerId] || ASR_PROVIDER_DEFAULTS.openai_compatible;
  handleConfigChange("ASR_PROVIDER", providerId);
  handleConfigChange("ASR_BASE_URL", defaults.url);
  handleConfigChange("WHISPER_BASE_URL", defaults.url);
  if (defaults.batchUrl) {
    handleConfigChange("ASR_BATCH_URL", defaults.batchUrl);
  }
  const model = defaults.models[0] || "";
  handleConfigChange("ASR_MODEL", model);
  handleConfigChange("WHISPER_MODEL", model);
};
