import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./utils";
import AppRoutes from "../components/layout/AppRoutes";
import TopNav from "../components/layout/TopNav";
import { WorkspaceProvider } from "../utils/context/workspaceContext";

vi.mock("../utils/api/workspaceApi", () => ({
    workspaceApi: {
        fetchSpecialties: vi.fn(async () => ({
            specialties: [
                {
                    id: "Cardiology",
                    fa: "قلب و عروق",
                    en: "Cardiology",
                    blurb: "درد قفسه سینه، فشار خون، آریتمی و نارسایی قلب",
                },
                {
                    id: "General Practice",
                    fa: "پزشکی عمومی",
                    en: "General Practice",
                    blurb: "ویزیت‌های روزمره",
                },
            ],
        })),
        fetchStatus: vi.fn(async () => ({
            specialty: "",
            name: "",
            llm_ready: true,
            asr_ready: true,
            llm_provider: "groq",
            asr_provider: "local",
        })),
        searchDictionary: vi.fn(async () => ({
            query: "",
            matches: [{ fa: "تب", en: "fever", cat: "symptoms" }],
            total: 1,
        })),
        generateReport: vi.fn(),
    },
}));

vi.mock("../utils/api/settingsApi", () => ({
    settingsApi: {
        fetchServerStatus: vi.fn(async () => ({
            llm: true,
            whisper: true,
            embedding: null,
        })),
        fetchUserSettings: vi.fn(async () => ({
            name: "",
            specialty: "",
            has_completed_splash_screen: true,
        })),
        saveUserSettings: vi.fn(async () => ({})),
        markSplashCompleted: vi.fn(async () => ({})),
        fetchConfig: vi.fn(async () => ({
            LLM_PROVIDER: "groq",
            LLM_BASE_URL: "https://api.groq.com/openai",
            ASR_PROVIDER: "local",
        })),
        fetchProviders: vi.fn(async () => ({
            llm: [
                { id: "groq", name: "Groq", name_fa: "Groq" },
                { id: "openrouter", name: "OpenRouter", name_fa: "OpenRouter" },
            ],
            asr: [],
        })),
        validateUrl: vi.fn(async () => true),
        saveConfig: vi.fn(async () => ({})),
    },
}));

function renderApp(path = "/") {
    return renderWithProviders(
        <MemoryRouter initialEntries={[path]}>
            <WorkspaceProvider>
                <TopNav />
                <AppRoutes />
            </WorkspaceProvider>
        </MemoryRouter>,
    );
}

describe("three-page clinician workspace", () => {
    beforeEach(() => {
        sessionStorage.clear();
        localStorage.clear();
    });

    it("shows specialty first and the three top-nav pages", async () => {
        renderApp("/");
        expect(screen.getByText("تخصص")).toBeInTheDocument();
        expect(screen.getByText("پیاده‌سازی")).toBeInTheDocument();
        expect(screen.getByText("تنظیمات")).toBeInTheDocument();
        await waitFor(() => {
            expect(screen.getByText("قلب و عروق")).toBeInTheDocument();
        });
        expect(screen.queryByText("گفت‌وگو با فلوکس")).not.toBeInTheDocument();
        expect(screen.queryByText("بیمار جدید")).not.toBeInTheDocument();
    });

    it("opens the transcription workspace without chat or patient entry", async () => {
        renderApp("/workspace");
        await waitFor(() => {
            expect(screen.getByText("پیاده‌سازی و گزارش")).toBeInTheDocument();
        });
        expect(screen.getByText("شروع ضبط")).toBeInTheDocument();
        expect(screen.getByText("تولید گزارش")).toBeInTheDocument();
        expect(screen.getByText("واژه‌نامه فارسی–انگلیسی")).toBeInTheDocument();
        expect(screen.queryByText("شماره پرونده")).not.toBeInTheDocument();
        expect(screen.queryByText("Chat dashboard")).not.toBeInTheDocument();
    });
});
