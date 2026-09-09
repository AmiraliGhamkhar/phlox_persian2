import { handleApiRequest, universalFetch } from "../helpers/apiHelpers";
import { buildApiUrl } from "../helpers/apiConfig";

export const workspaceApi = {
    fetchSpecialties: async () =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/workspace/specialties");
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to fetch specialties",
        }),

    fetchStatus: async () =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/workspace/status");
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to fetch workspace status",
        }),

    searchDictionary: async (query = "", limit = 20) => {
        const params = new URLSearchParams();
        if (query) params.set("q", query);
        params.set("limit", String(limit));
        return handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl(
                    `/api/workspace/dictionary?${params.toString()}`,
                );
                return universalFetch(url, { signal });
            },
            errorMessage: "Failed to search dictionary",
        });
    },

    generateReport: async (payload) =>
        handleApiRequest({
            apiCall: async (signal) => {
                const url = await buildApiUrl("/api/workspace/report");
                return universalFetch(url, {
                    signal,
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
            },
            timeout: 180000,
            errorMessage: "Failed to generate report",
        }),
};
