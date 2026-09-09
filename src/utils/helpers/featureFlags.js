import { isTauri } from "./apiConfig";

/**
 * Chat and patient-list UI are removed from the simplified three-page app.
 */
export const isChatEnabled = () => {
  return false;
};

// Embedding model status — cached in localStorage for synchronous access.
// Updated by setEmbeddingReady() when download status changes.
let embeddingReady = (() => {
  try {
    return localStorage.getItem("embedding-model-ready") === "true";
  } catch {
    return false;
  }
})();

export const setEmbeddingReady = (ready) => {
  embeddingReady = ready;
  try {
    localStorage.setItem("embedding-model-ready", ready ? "true" : "false");
  } catch {}
};

/**
 * Check if RAG (document knowledge base) features are enabled.
 * - Web/Docker: always enabled (uses external embedding service).
 * - Tauri (desktop): enabled only if the local embedding model is downloaded.
 */
export const isRagEnabled = () => {
  if (isTauri()) return embeddingReady;
  return true;
};

/**
 * Check if PDF form template features are enabled.
 * No dependency on sqlite-vec or vector embeddings — always available.
 */
export const isPdfFormsEnabled = () => {
  return true;
};

//Turn off forced splash screen for normal dev work with `VITE_FORCE_SPLASH=false tauri dev`.
export const isForceSplashEnabled = () => {
  return false;
};
