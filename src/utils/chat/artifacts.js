/**
 * Normalize artifact payloads from chat SSE / confirm-action JSON
 * into the shape ArtifactCard / FormFillArtifact expect.
 */
export function normalizeChatArtifacts(rawArtifacts = []) {
    if (!Array.isArray(rawArtifacts) || rawArtifacts.length === 0) {
        return [];
    }

    return rawArtifacts
        .map((artifact) => {
            if (!artifact || typeof artifact !== "object") {
                return null;
            }
            if (artifact.type === "form_fill" || !artifact.data) {
                return artifact;
            }

            const { data: b64Data, ...meta } = artifact;
            try {
                const binary = atob(b64Data);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) {
                    bytes[i] = binary.charCodeAt(i);
                }
                const blob = new Blob([bytes], {
                    type: meta.mime_type || "application/octet-stream",
                });
                return { ...meta, url: URL.createObjectURL(blob) };
            } catch {
                return { ...meta };
            }
        })
        .filter(Boolean);
}
