import { handleApiRequest, universalFetch } from "../helpers/apiHelpers";
import { buildApiUrl } from "../helpers/apiConfig";

export const settingsApi = {
    fetchUserSettings: async () =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/config/user");
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to fetch user settings",
        }),

    fetchConfig: async () =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/config/global");
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to fetch config",
        }),

    // New method to fetch models for any LLM provider
    fetchLLMModels: async (providerType, baseUrl, apiKey = null) => {
        // Omit baseUrl when empty — URLSearchParams would stringify a null/
        // undefined value to the literal "null", which the backend would
        // treat as a real (garbage) URL.
        const params = new URLSearchParams();
        params.append("provider", providerType);
        if (baseUrl) {
            params.append("baseUrl", baseUrl);
        }

        if (apiKey) {
            params.append("apiKey", apiKey);
        }

        const endpoint = `/api/config/llm/models?${params.toString()}`;

        return handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl(endpoint);
                return universalFetch(url, { signal });
            },
            errorMessage: `Failed to fetch ${providerType} models`,
        });
    },

    fetchProviders: async () =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/config/providers");
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to fetch AI providers",
        }),

    fetchWhisperModels: async (whisperBaseUrl, provider = null, apiKey = null) => {
        const params = new URLSearchParams();
        if (whisperBaseUrl) params.append("asrEndpoint", whisperBaseUrl);
        if (provider) params.append("provider", provider);
        if (apiKey) params.append("apiKey", apiKey);
        if (!whisperBaseUrl && !provider) {
            return Promise.resolve({ models: [], listAvailable: false });
        }
        const endpoint = `/api/config/asr/models?${params.toString()}`;
        return handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl(endpoint);
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to fetch ASR models",
        });
    },

    saveConfig: async (config) =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/config/global");
                return universalFetch(url, {
                    signal,
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(config),
                });
            },
            errorMessage: "Failed to save config",
        }),

    saveUserSettings: async (userSettings) =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/config/user");
                return universalFetch(url, {
                    signal,
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(userSettings),
                });
            },
            errorMessage: "Failed to save user settings",
        }),

    validateUrl: async (type: string, url: string) => {
        if (!url) return false;
        const params = new URLSearchParams({
            url,
            type,
        });
        try {
            const data: any = await handleApiRequest({
                apiCall: async (signal) => {
                    const fullUrl = await buildApiUrl(
                        `/api/config/validate-url?${params.toString()}`,
                    );
                    return universalFetch(fullUrl, { signal });
                },
                errorMessage: `Failed to validate ${type} URL`,
            });
            return Boolean(data?.valid);
        } catch (error) {
            console.error(`Error validating ${type} URL:`, error);
            return false;
        }
    },

    markSplashCompleted: async () =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl(
                    "/api/config/user/mark_splash_complete",
                );
                return universalFetch(url, { signal, method: "POST" });
            },
            errorMessage: "Failed to mark splash screen as complete",
        }),

    fetchServerStatus: async (signal?: AbortSignal) => {
        const url = await buildApiUrl("/api/config/status");
        const response = await universalFetch(url, { signal });
        if (!response.ok) {
            let detail;
            try {
                const errorData = await response.json();
                detail = errorData.detail || errorData.message;
            } catch {
                // No JSON body
            }
            throw new Error(
                detail || `HTTP error! status: ${response.status}`,
            );
        }
        return response.json();
    },
};
