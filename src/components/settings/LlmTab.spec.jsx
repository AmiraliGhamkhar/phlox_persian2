import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, cleanup } from "@testing-library/react";
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
});
