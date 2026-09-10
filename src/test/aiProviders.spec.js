import { describe, expect, it } from "vitest";
import {
    applyAsrProviderDefaults,
    applyLlmProviderDefaults,
} from "../utils/aiProviders";

const collect = () => {
    const changes = {};
    return [changes, (key, value) => {
        changes[key] = value;
    }];
};

describe("applyLlmProviderDefaults", () => {
    it("fills the provider default URL when the field is empty", () => {
        const [changes, apply] = collect();
        applyLlmProviderDefaults("ollama", apply, "");
        expect(changes.LLM_BASE_URL).toBe("http://127.0.0.1:11434");
        expect(changes.LLM_PROVIDER).toBe("ollama");
    });

    it("overwrites a URL that is just another provider's default", () => {
        const [changes, apply] = collect();
        applyLlmProviderDefaults(
            "openai",
            apply,
            "http://127.0.0.1:11434", // ollama default
        );
        expect(changes.LLM_BASE_URL).toBe("https://api.openai.com");
    });

    it("keeps a customized base URL across provider switches", () => {
        const [changes, apply] = collect();
        applyLlmProviderDefaults(
            "groq",
            apply,
            "http://gateway.internal:8080/v1",
        );
        expect(changes.LLM_PROVIDER).toBe("groq");
        expect(changes.LLM_BASE_URL).toBeUndefined();
    });

    it("never auto-fills the URL for the custom-compatible provider", () => {
        const [changes, apply] = collect();
        applyLlmProviderDefaults("openai_compatible", apply, "");
        expect(changes.LLM_BASE_URL).toBeUndefined();
    });
});

describe("applyAsrProviderDefaults", () => {
    it("keeps customized ASR URLs but still applies the model", () => {
        const [changes, apply] = collect();
        applyAsrProviderDefaults(
            "openai",
            apply,
            "http://asr.internal:9000",
            "",
        );
        expect(changes.ASR_BASE_URL).toBeUndefined();
        expect(changes.WHISPER_BASE_URL).toBeUndefined();
        expect(changes.ASR_MODEL).toBeTruthy();
    });

    it("fills defaults when the fields are empty", () => {
        const [changes, apply] = collect();
        applyAsrProviderDefaults("speechmatics", apply, "", "");
        expect(changes.ASR_BASE_URL).toBe("wss://global.rt.speechmatics.com/v2");
        expect(changes.ASR_BATCH_URL).toBe(
            "https://eu1.asr.api.speechmatics.com/v2",
        );
    });

    it("keeps a customized batch URL", () => {
        const [changes, apply] = collect();
        applyAsrProviderDefaults(
            "speechmatics",
            apply,
            "",
            "https://batch.internal:9443/v2",
        );
        expect(changes.ASR_BATCH_URL).toBeUndefined();
    });
});
