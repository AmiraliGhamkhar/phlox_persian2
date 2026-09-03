import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, cleanup } from "@testing-library/react";
import { renderWithProviders } from "../../test/utils";
import ModelSettingsPanel from "./ModelSettingsPanel";

// Stub the heavy tab children — this inventory covers the panel's tab
// structure (which tabs exist, in which branch, which is selected by
// default), not the internals of each tab.
vi.mock("./LlmTab", () => ({
    default: () => <div data-testid="llm-tab-body" />,
}));
vi.mock("./WhisperTab", () => ({
    default: () => <div data-testid="whisper-tab-body" />,
}));
vi.mock("./RagTab", () => ({
    default: () => <div data-testid="rag-tab-body" />,
}));
vi.mock("./ToolsSettingsTab", () => ({
    default: () => <div data-testid="tools-tab-body" />,
}));
vi.mock("./LocalModelManager", () => ({
    default: () => <div data-testid="local-model-manager-body" />,
}));
vi.mock("../../utils/api/localModelApi", () => ({
    localModelApi: {
        checkLocalStatus: vi.fn(async () => ({ available: false })),
    },
}));
vi.mock("../../utils/helpers/apiConfig", () => ({
    isTauri: () => false,
    buildApiUrl: vi.fn(async (endpoint) => `http://api.test${endpoint}`),
}));
vi.mock("../../utils/helpers/apiHelpers", () => ({
    universalFetch: vi.fn(async () => ({
        ok: true,
        json: async () => ({ is_docker: false }),
    })),
}));

const renderPanel = (config) =>
    renderWithProviders(
        <ModelSettingsPanel
            isCollapsed={false}
            setIsCollapsed={() => {}}
            config={config}
            handleConfigChange={() => {}}
        />,
    );

describe("ModelSettingsPanel — control inventory", () => {
    afterEach(cleanup);

    it("remote mode offers the ASR, LLM, KB and Tools tabs", () => {
        renderPanel({ LLM_PROVIDER: "openai_compatible" });

        const tabs = screen.getAllByRole("tab");
        expect(tabs).toHaveLength(4);
        expect(new Set(tabs.map((t) => t.dataset.testid))).toEqual(
            new Set([
                "remote-tab-asr",
                "remote-tab-llm",
                "remote-tab-rag",
                "remote-tab-tools",
            ]),
        );
    });

    it("remote mode selects exactly one tab by default — the first trigger", () => {
        renderPanel({ LLM_PROVIDER: "openai_compatible" });

        const tabs = screen.getAllByRole("tab");
        const selected = tabs.filter(
            (t) => t.getAttribute("aria-selected") === "true",
        );
        expect(selected).toHaveLength(1);
        expect(selected[0]).toBe(tabs[0]);
    });

    it("local mode offers the Models and Tools tabs only", () => {
        renderPanel({ LLM_PROVIDER: "local" });

        const tabs = screen.getAllByRole("tab");
        expect(tabs.map((t) => t.dataset.testid)).toEqual([
            "local-tab-models",
            "local-tab-tools",
        ]);
    });
});
