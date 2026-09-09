import { handleApiRequest, universalFetch } from "../helpers/apiHelpers";
import { buildApiUrl, isTauri } from "../helpers/apiConfig";
import { invoke } from "@tauri-apps/api/core";
import { streamSSEEvents } from "./sseStream";

export const localModelApi = {
  // Streaming download helper for SSE. Buffered parsing so an event split
  // across TCP reads is reassembled instead of dropped — losing the final
  // "complete" frame would skip the sidecar restart and leave the UI stuck.
  // Yields `any` (not `unknown`) so callers keep their existing untyped event
  // access (e.g. `event.type`) — same surface as the original parser.
  streamSSE: async function* (url): AsyncGenerator<any> {
    yield* streamSSEEvents(url);
  },

  // LLM Model Management (llama-server)
  fetchAvailableLlmModels: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/models/available");
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch available LLM models",
    }),

  fetchLocalModels: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/models");
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch local models",
    }),

  fetchModelRecommendations: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(
          "/api/config/local/model-recommendations",
        );
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch model recommendations",
    }),

  checkLocalStatus: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/status");
        return universalFetch(url);
      },
      errorMessage: "Failed to check local status",
    }),

  downloadLlmModel: async (modelId) =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/models/download");
        return universalFetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: modelId }),
        });
      },
      successMessage: "Model downloaded successfully",
      errorMessage: "Failed to download model",
      timeout: 600000, // 10 minutes for larger models
    }),

  streamDownloadLlmModel: async function* (modelId) {
    const baseUrl = await buildApiUrl("");
    const url = `${baseUrl}/api/config/local/models/download/stream?model_id=${encodeURIComponent(modelId)}`;
    yield* this.streamSSE(url);
  },

  deleteLlmModel: async (filename) =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(`/api/config/local/models/${filename}`);
        return universalFetch(url, {
          method: "DELETE",
        });
      },
      successMessage: "Model deleted successfully",
      errorMessage: "Failed to delete model",
    }),

  restartLlamaServer: async () => {
    // invoke() returns a plain object, not a fetch Response — do not run it
    // through handleApiRequest (that helper requires `response.ok`).
    if (isTauri()) {
      return invoke("restart_llama");
    }
    // Docker/browser: the API server restarts the sidecar itself after a
    // download or select, so there is nothing for the UI to do.
    return { restarted: true, manager: "backend" };
  },

  getSelectedModel: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/selected-model");
        return universalFetch(url);
      },
      errorMessage: "Failed to get selected model",
    }),

  // ASR model management
  fetchWhisperModels: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(
          "/api/config/local/asr/models/downloaded",
        );
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch ASR models",
    }),

  fetchDownloadedWhisperModels: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(
          "/api/config/local/asr/models/downloaded",
        );
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch downloaded ASR models",
    }),

  fetchAvailableWhisperModels: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(
          "/api/config/local/asr/models/available",
        );
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch available ASR models",
    }),

  fetchWhisperRecommendations: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(
          "/api/config/local/asr/model-recommendations",
        );
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch ASR model recommendations",
    }),

  streamDownloadWhisperModel: async function* (modelId) {
    const baseUrl = await buildApiUrl("");
    const url = `${baseUrl}/api/config/local/asr/models/download/stream?model_id=${encodeURIComponent(modelId)}`;
    yield* this.streamSSE(url);
  },

  selectWhisperModel: async (modelId) =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/asr/models/select");
        return universalFetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: modelId }),
        });
      },
      successMessage: "ASR model selected",
      errorMessage: "Failed to select ASR model",
    }),

  deleteWhisperModel: async (modelId) =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl(
          `/api/config/local/asr/models/${modelId}`,
        );
        return universalFetch(url, {
          method: "DELETE",
        });
      },
      successMessage: "ASR model deleted successfully",
      errorMessage: "Failed to delete ASR model",
    }),

  fetchWhisperStatus: async () =>
    handleApiRequest({
      apiCall: async () => {
        const url = await buildApiUrl("/api/config/local/asr/status");
        return universalFetch(url);
      },
      errorMessage: "Failed to fetch ASR status",
    }),

  restartWhisperServer: async () =>
    handleApiRequest({
      apiCall: async () => {
        if (isTauri()) {
          return await invoke("restart_whisper");
        }
        // Docker/browser: the API server restarts the sidecar itself after a
        // download or select, so there is nothing for the UI to do.
        return { restarted: true, manager: "backend" };
      },
      successMessage: "Whisper server restarted successfully",
      errorMessage: "Failed to restart Whisper server",
    }),
};
