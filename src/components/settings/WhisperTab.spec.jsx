import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import WhisperTab from "./WhisperTab";

/**
 * Control inventory for WhisperTab — the baseline for the T1-2 Advanced
 * expander. Controls are asserted by data-testid (not label text, so the
 * T1-4 Persian copy pass stays covered) and by DOM presence, so the
 * inventory stays valid when the URL/key/model trio moves behind a
 * collapsed expander (Chakra keeps Collapsible.Content mounted).
 */
describe("WhisperTab — control inventory", () => {
    afterEach(cleanup);

    const renderWhisperTab = (config = {}, handleConfigChange = vi.fn()) =>
        renderWithProviders(
            <WhisperTab
                config={config}
                handleConfigChange={handleConfigChange}
                whisperModelOptions={["whisper-large-v3-turbo"]}
                whisperModelListAvailable={false}
                urlStatus={{ whisper: true }}
            />,
        );

    it("cloud provider: provider, language, base URL, model and API key are present", () => {
        renderWhisperTab({ ASR_PROVIDER: "openai_compatible" });

        expect(screen.getByTestId("asr-provider-select")).toBeInTheDocument();
        expect(screen.getByTestId("asr-language-select")).toBeInTheDocument();
        expect(screen.getByTestId("asr-base-url-input")).toBeInTheDocument();
        expect(screen.getByTestId("asr-model-control")).toBeInTheDocument();
        expect(screen.getByTestId("asr-api-key-input")).toBeInTheDocument();
        // Speechmatics-only controls must not render for other providers
        expect(screen.queryByTestId("asr-batch-url-input")).not.toBeInTheDocument();
        expect(screen.queryByTestId("asr-batch-key-input")).not.toBeInTheDocument();
    });

    it("speechmatics: the batch URL/key pair appears", () => {
        renderWhisperTab({ ASR_PROVIDER: "speechmatics" });

        expect(screen.getByTestId("asr-batch-url-input")).toBeInTheDocument();
        expect(screen.getByTestId("asr-batch-key-input")).toBeInTheDocument();
    });

    it("local provider: no base URL or API key, model control stays", () => {
        renderWhisperTab({ ASR_PROVIDER: "local" });

        expect(screen.queryByTestId("asr-base-url-input")).not.toBeInTheDocument();
        expect(screen.queryByTestId("asr-api-key-input")).not.toBeInTheDocument();
        expect(screen.getByTestId("asr-provider-select")).toBeInTheDocument();
        expect(screen.getByTestId("asr-language-select")).toBeInTheDocument();
        expect(screen.getByTestId("asr-model-control")).toBeInTheDocument();
    });

    it("binds the controls to the config values", () => {
        renderWhisperTab({
            ASR_PROVIDER: "openai_compatible",
            ASR_LANGUAGE: "fa",
            ASR_BASE_URL: "https://asr.example.com/v1",
            ASR_KEY: "asr-key-123",
            ASR_BATCH_URL: "https://batch.example.com/v2",
            ASR_BATCH_KEY: "batch-key-456",
        });
        expect(screen.getByTestId("asr-provider-select")).toHaveValue(
            "openai_compatible",
        );
        expect(screen.getByTestId("asr-language-select")).toHaveValue("fa");
        expect(screen.getByTestId("asr-base-url-input")).toHaveValue(
            "https://asr.example.com/v1",
        );
        expect(screen.getByTestId("asr-api-key-input")).toHaveValue(
            "asr-key-123",
        );
    });

    it("provider switch applies the ASR defaults through handleConfigChange", () => {
        const handleConfigChange = vi.fn();
        renderWhisperTab({ ASR_PROVIDER: "openai_compatible" }, handleConfigChange);

        fireEvent.change(screen.getByTestId("asr-provider-select"), {
            target: { value: "speechmatics" },
        });

        expect(handleConfigChange).toHaveBeenCalledWith(
            "ASR_PROVIDER",
            "speechmatics",
        );
        // Dual-key legacy behavior: base URL is written to both keys
        expect(handleConfigChange.mock.calls.filter(([key]) => key === "ASR_BASE_URL")).toHaveLength(1);
        expect(handleConfigChange.mock.calls.filter(([key]) => key === "WHISPER_BASE_URL")).toHaveLength(1);
        expect(handleConfigChange.mock.calls.filter(([key]) => key === "ASR_MODEL")).toHaveLength(1);
        expect(handleConfigChange.mock.calls.filter(([key]) => key === "WHISPER_MODEL")).toHaveLength(1);
    });

    it("language change is written to both the ASR and legacy WHISPER keys", () => {
        const handleConfigChange = vi.fn();
        renderWhisperTab({ ASR_PROVIDER: "openai_compatible" }, handleConfigChange);

        fireEvent.change(screen.getByTestId("asr-language-select"), {
            target: { value: "en" },
        });

        expect(handleConfigChange).toHaveBeenCalledWith("ASR_LANGUAGE", "en");
        expect(handleConfigChange).toHaveBeenCalledWith("WHISPER_LANGUAGE", "en");
    });

    it("model change is written to both the ASR and legacy WHISPER keys", () => {
        const handleConfigChange = vi.fn();
        renderWhisperTab({ ASR_PROVIDER: "openai_compatible" }, handleConfigChange);

        const modelInput = screen.getByTestId("asr-model-control").querySelector("input");
        fireEvent.change(modelInput, { target: { value: "whisper-large-v3" } });

        expect(handleConfigChange).toHaveBeenCalledWith(
            "ASR_MODEL",
            "whisper-large-v3",
        );
        expect(handleConfigChange).toHaveBeenCalledWith(
            "WHISPER_MODEL",
            "whisper-large-v3",
        );
    });

    it("keeps the URL/key/model trio collapsed; provider and language stay visible", () => {
        renderWhisperTab({ ASR_PROVIDER: "openai_compatible" });

        const toggle = screen.getByTestId("asr-advanced-toggle");
        expect(toggle).toBeVisible();
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        for (const id of [
            "asr-base-url-input",
            "asr-model-control",
            "asr-api-key-input",
        ]) {
            expect(screen.getByTestId(id)).not.toBeVisible();
        }
        expect(screen.getByTestId("asr-provider-select")).toBeVisible();
        expect(screen.getByTestId("asr-language-select")).toBeVisible();
    });

    it("reveals the trio on toggle and preserves their values", async () => {
        renderWhisperTab({
            ASR_PROVIDER: "openai_compatible",
            ASR_BASE_URL: "https://x.example/v1",
            ASR_KEY: "k123",
        });

        fireEvent.click(screen.getByTestId("asr-advanced-toggle"));
        await waitFor(() =>
            expect(screen.getByTestId("asr-advanced-toggle")).toHaveAttribute(
                "aria-expanded",
                "true",
            ),
        );
        // Chakra's collapsible machine syncs the controlled `open` prop
        // asynchronously (zag microtask), so wait for the content state.
        const content = screen
            .getByTestId("asr-base-url-input")
            .closest("[data-state]");
        await waitFor(() =>
            expect(content).toHaveAttribute("data-state", "open"),
        );
        expect(content).not.toHaveAttribute("hidden");
        for (const id of [
            "asr-base-url-input",
            "asr-model-control",
            "asr-api-key-input",
        ]) {
            expect(screen.getByTestId(id)).toBeInTheDocument();
        }
        // Values survived the collapse/expand round-trip
        expect(screen.getByTestId("asr-base-url-input")).toHaveValue(
            "https://x.example/v1",
        );
        expect(screen.getByTestId("asr-api-key-input")).toHaveValue("k123");
    });
});
