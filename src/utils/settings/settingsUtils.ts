import { settingsApi } from "../api/settingsApi";

export const settingsService = {
    fetchLLMModels: async (config, setModelOptions) => {
        try {
            const providerType = config.LLM_PROVIDER || "ollama";

            // For local models, we don't need base URL
            if (providerType === "local") {
                const response = await settingsApi.fetchLLMModels(
                    providerType,
                    null,
                    null,
                );
                setModelOptions(response.models || []);
                return;
            }

            // For remote providers, base URL is required
            if (!config.LLM_BASE_URL) {
                setModelOptions([]);
                return;
            }

            const baseUrl = config.LLM_BASE_URL;

            const rawKey = config.LLM_API_KEY || "";
            const apiKey = rawKey.includes("•") ? null : rawKey;

            const response = await settingsApi.fetchLLMModels(
                providerType,
                baseUrl,
                apiKey,
            );

            const models = (response.models || []).map((model) =>
                typeof model === "string" ? model : model?.name || model?.id,
            );
            setModelOptions(models.filter(Boolean));
        } catch (error) {
            console.error(
                `Error fetching ${config.LLM_PROVIDER} models:`,
                error,
            );
            setModelOptions([]);
        }
    },

    fetchWhisperModels: async (
        whisperBaseUrl,
        setWhisperModelOptions,
        setWhisperModelListAvailable,
        provider = null,
        apiKey = null,
    ) => {
        try {
            const response = await settingsApi.fetchWhisperModels(
                whisperBaseUrl,
                provider,
                apiKey,
            );
            setWhisperModelOptions(response?.models || []);
            if (setWhisperModelListAvailable) {
                setWhisperModelListAvailable(Boolean(response?.listAvailable));
            }
            return response;
        } catch (error) {
            console.error("Error fetching ASR models:", error);
            return { models: [], listAvailable: false };
        }
    },
};
