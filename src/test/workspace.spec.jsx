import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router";
import { screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
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

    afterEach(() => {
        // No vitest globals -> no automatic unmount; drop each render so
        // queries never see elements from a previous test.
        cleanup();
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

    it("shows the amber review banner when the generated note has faithfulness warnings", async () => {
        const { workspaceApi } = await import("../utils/api/workspaceApi");
        workspaceApi.generateReport.mockResolvedValueOnce({
            report: {
                chief_complaint: "پیگیری دیابت",
                history: "",
                examination: "",
                assessment: "",
                plan: "",
                full_note: "",
            },
            full_note: "شکایت اصلی: پیگیری دیابت.\nتست‌ها: HbA1c 8.1 درصد.",
            dictionary: [],
            process_duration: 0.1,
            warnings: [
                {
                    kind: "number_drift",
                    detail: "عدد 8.1 در یادداشت هست ولی در متن ورودی نیامده است",
                    span: "8.1",
                },
            ],
        });

        renderApp("/workspace");
        const textarea = await screen.findByPlaceholderText(
            "اینجا صحبت کنید یا متن را بنویسید...",
        );
        fireEvent.change(textarea, {
            target: { value: "بیمار دیابت دارد. HbA1c در حد 7.2 درصد بود." },
        });
        fireEvent.click(screen.getByText("تولید گزارش"));

        const banner = await screen.findByTestId("verification-warnings");
        expect(banner.textContent).toContain("تغییر عدد");
        expect(banner.textContent).toContain("8.1");
        // The (drifted) note is still shown — warnings never block.
        expect(screen.getByText(/HbA1c 8\.1 درصد/)).toBeInTheDocument();
        expect(workspaceApi.generateReport).toHaveBeenCalledTimes(1);
    });

    it("does not show the review banner for a clean report", async () => {
        const { workspaceApi } = await import("../utils/api/workspaceApi");
        workspaceApi.generateReport.mockResolvedValueOnce({
            report: {
                chief_complaint: "درد قفسه سینه",
                history: "",
                examination: "",
                assessment: "",
                plan: "",
                full_note: "",
            },
            full_note: "شکایت اصلی: درد قفسه سینه از دیروز.",
            dictionary: [],
            process_duration: 0.1,
            warnings: [],
        });

        renderApp("/workspace");
        const textarea = await screen.findByPlaceholderText(
            "اینجا صحبت کنید یا متن را بنویسید...",
        );
        fireEvent.change(textarea, {
            target: { value: "بیمار از دیروز درد قفسه سینه دارد." },
        });
        fireEvent.click(screen.getByText("تولید گزارش"));

        await waitFor(() => {
            expect(screen.getByText(/درد قفسه سینه از دیروز/)).toBeInTheDocument();
        });
        expect(
            screen.queryByTestId("verification-warnings"),
        ).not.toBeInTheDocument();
    });
});
