import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import LlmTab from "./LlmTab";

vi.mock("../../utils/api/chatApi", () => ({
    chatApi: {
        getCurrentVisionCapability: vi.fn(async () => null),
        probeVisionCapability: vi.fn(async () => ({ vision_capable: true })),
    },
}));

const renderLlmTab = (config = {}, handleConfigChange = vi.fn()) =>
    renderWithProviders(
        <LlmTab
            config={config}
            handleConfigChange={handleConfigChange}
            modelOptions={["model-a", "model-b"]}
            llmProviders={[
                { id: "ollama", name: "Ollama" },
                { id: "openai", name: "OpenAI" },
            ]}
            urlStatus={{ llm: true }}
        />,
    );

/**
 * Control inventory for LlmTab — the baseline for the T1-1 "Advanced"
 * expander. Controls are asserted by data-testid (not label text) so the
 * inventory stays valid through the T1-4 Persian copy pass, and presence is
 * DOM-based so it stays valid when the expert controls move behind a
 * collapsed expander (Chakra keeps Collapsible.Content mounted).
 */
describe("LlmTab — control inventory", () => {
    afterEach(cleanup);

    it("renders all seven controls", () => {
        renderLlmTab();
        for (const id of [
            "llm-provider-select",
            "llm-base-url-input",
            "llm-api-key-input",
            "llm-primary-model-select",
            "llm-secondary-model-select",
            "llm-processing-mode-select",
            "llm-vision-probe-button",
        ]) {
            expect(screen.getByTestId(id)).toBeInTheDocument();
        }
    });

    it("the four core fields are visible without any interaction", () => {
        renderLlmTab();
        for (const id of [
            "llm-provider-select",
            "llm-base-url-input",
            "llm-api-key-input",
            "llm-primary-model-select",
        ]) {
            expect(screen.getByTestId(id)).toBeVisible();
        }
    });

    it("binds the core fields to the config values", () => {
        renderLlmTab({
            LLM_PROVIDER: "openai",
            LLM_BASE_URL: "https://api.openai.com/v1",
            LLM_API_KEY: "sk-test",
            PRIMARY_MODEL: "model-b",
        });
        expect(screen.getByTestId("llm-provider-select")).toHaveValue(
            "openai",
        );
        expect(screen.getByTestId("llm-base-url-input")).toHaveValue(
            "https://api.openai.com/v1",
        );
        expect(screen.getByTestId("llm-api-key-input")).toHaveValue("sk-test");
        expect(screen.getByTestId("llm-primary-model-select")).toHaveValue(
            "model-b",
        );
    });

    it("binds the expert controls to the config values", () => {
        renderLlmTab({
            SECONDARY_MODEL: "model-a",
            DOCUMENT_IMAGE_PROCESSING_MODE: "vision",
        });
        expect(screen.getByTestId("llm-secondary-model-select")).toHaveValue(
            "model-a",
        );
        expect(screen.getByTestId("llm-processing-mode-select")).toHaveValue(
            "vision",
        );
    });

    it("keeps the expert controls collapsed behind the Advanced toggle", () => {
        renderLlmTab();

        const toggle = screen.getByTestId("llm-advanced-toggle");
        expect(toggle).toBeVisible();
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        for (const id of [
            "llm-secondary-model-select",
            "llm-processing-mode-select",
            "llm-vision-probe-button",
        ]) {
            expect(screen.getByTestId(id)).not.toBeVisible();
        }
    });

    it("reveals the expert controls on toggle and preserves their values", async () => {
        renderLlmTab({
            SECONDARY_MODEL: "model-a",
            DOCUMENT_IMAGE_PROCESSING_MODE: "vision",
        });

        fireEvent.click(screen.getByTestId("llm-advanced-toggle"));
        await waitFor(() =>
            expect(screen.getByTestId("llm-advanced-toggle")).toHaveAttribute(
                "aria-expanded",
                "true",
            ),
        );
        // Chakra's collapsible machine syncs the controlled `open` prop
        // asynchronously (zag microtask), so wait for the content state.
        const content = screen
            .getByTestId("llm-secondary-model-select")
            .closest("[data-state]");
        await waitFor(() =>
            expect(content).toHaveAttribute("data-state", "open"),
        );
        expect(content).not.toHaveAttribute("hidden");
        for (const id of [
            "llm-secondary-model-select",
            "llm-processing-mode-select",
            "llm-vision-probe-button",
        ]) {
            expect(screen.getByTestId(id)).toBeInTheDocument();
        }
        // Values survived the collapse/expand round-trip
        expect(screen.getByTestId("llm-secondary-model-select")).toHaveValue(
            "model-a",
        );
        expect(screen.getByTestId("llm-processing-mode-select")).toHaveValue(
            "vision",
        );
    });
});
