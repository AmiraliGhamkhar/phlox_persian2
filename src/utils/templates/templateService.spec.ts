import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../helpers/apiConfig", () => ({
    buildApiUrl: vi.fn(),
}));
vi.mock("../helpers/apiHelpers", () => ({
    universalFetch: vi.fn(),
}));
vi.mock("../api/settingsApi", () => ({
    settingsApi: { setDefaultTemplate: vi.fn() },
}));
vi.mock("../helpers/settingsHelpers", () => ({
    settingsHelpers: { showSuccessToast: vi.fn(), showErrorToast: vi.fn() },
}));

import { templateService } from "./templateService";
import { buildApiUrl } from "../helpers/apiConfig";
import { universalFetch } from "../helpers/apiHelpers";
import { settingsApi } from "../api/settingsApi";
import { settingsHelpers } from "../helpers/settingsHelpers";

/**
 * Characterization spec (T2-4A) for the templateService methods that
 * Settings.jsx relies on: fetchTemplates, getDefaultTemplate and
 * setDefaultTemplate.
 *
 * These pin the current behavior of utils/templates/templateService.ts so
 * the consolidation of the duplicate utils/services/templateService.ts
 * (pointing Settings.jsx at this module) can be proven behavior-neutral.
 */

const okJson = (data: unknown) =>
    ({ ok: true, json: async () => data } as unknown as Response);
const notOk = (status = 500) =>
    ({ ok: false, status, json: async () => ({}) } as unknown as Response);

describe("templateService (templates/) — methods used by Settings.jsx", () => {
    beforeEach(() => {
        vi.mocked(buildApiUrl).mockReset();
        vi.mocked(buildApiUrl).mockImplementation(
            async (endpoint: string) => `http://api.test${endpoint}`,
        );
        vi.mocked(universalFetch).mockReset();
        vi.mocked(settingsApi.setDefaultTemplate).mockReset();
        vi.mocked(settingsHelpers.showSuccessToast).mockReset();
        vi.mocked(settingsHelpers.showErrorToast).mockReset();
    });

    describe("fetchTemplates", () => {
        it("GETs /api/templates and returns the parsed JSON", async () => {
            vi.mocked(universalFetch).mockResolvedValue(okJson({ t1: {} }));

            const result = await templateService.fetchTemplates();

            expect(buildApiUrl).toHaveBeenCalledWith("/api/templates");
            expect(universalFetch).toHaveBeenCalledWith(
                "http://api.test/api/templates",
            );
            expect(result).toEqual({ t1: {} });
        });

        it("throws 'Failed to fetch templates' on a non-OK response", async () => {
            vi.mocked(universalFetch).mockResolvedValue(notOk(503));

            await expect(templateService.fetchTemplates()).rejects.toThrow(
                "Failed to fetch templates",
            );
        });

        it("rethrows transport errors", async () => {
            vi.mocked(universalFetch).mockRejectedValue(new Error("network"));

            await expect(templateService.fetchTemplates()).rejects.toThrow(
                "network",
            );
        });
    });

    describe("getDefaultTemplate", () => {
        it("GETs /api/templates/default and returns the parsed JSON", async () => {
            const payload = { template_key: "soap_default", name: "SOAP" };
            vi.mocked(universalFetch).mockResolvedValue(okJson(payload));

            const result = await templateService.getDefaultTemplate();

            expect(buildApiUrl).toHaveBeenCalledWith("/api/templates/default");
            expect(result).toEqual(payload);
        });

        it("throws 'Failed to fetch default template' on a non-OK response", async () => {
            vi.mocked(universalFetch).mockResolvedValue(notOk(404));

            await expect(templateService.getDefaultTemplate()).rejects.toThrow(
                "Failed to fetch default template",
            );
        });

        it("rethrows transport errors", async () => {
            vi.mocked(universalFetch).mockRejectedValue(new Error("offline"));

            await expect(templateService.getDefaultTemplate()).rejects.toThrow(
                "offline",
            );
        });
    });

    describe("setDefaultTemplate", () => {
        it("delegates to settingsApi.setDefaultTemplate and stays silent without a toast", async () => {
            vi.mocked(settingsApi.setDefaultTemplate).mockResolvedValue(
                okJson({}) as never,
            );

            await templateService.setDefaultTemplate("soap_default", undefined);

            expect(settingsApi.setDefaultTemplate).toHaveBeenCalledWith(
                "soap_default",
            );
            expect(settingsHelpers.showSuccessToast).not.toHaveBeenCalled();
            expect(settingsHelpers.showErrorToast).not.toHaveBeenCalled();
        });

        it("shows a success toast when a toast function is provided", async () => {
            const toast = (() => {}) as never;
            vi.mocked(settingsApi.setDefaultTemplate).mockResolvedValue(
                okJson({}) as never,
            );

            await templateService.setDefaultTemplate("soap_default", toast);

            expect(settingsHelpers.showSuccessToast).toHaveBeenCalledWith(
                toast,
                "Default template updated successfully",
            );
        });

        it("rethrows API errors without a toast", async () => {
            vi.mocked(settingsApi.setDefaultTemplate).mockRejectedValue(
                new Error("boom"),
            );

            await expect(
                templateService.setDefaultTemplate("soap_default", undefined),
            ).rejects.toThrow("boom");
            expect(settingsHelpers.showErrorToast).not.toHaveBeenCalled();
        });

        it("shows an error toast and rethrows when a toast function is provided", async () => {
            const toast = (() => {}) as never;
            vi.mocked(settingsApi.setDefaultTemplate).mockRejectedValue(
                new Error("boom"),
            );

            await expect(
                templateService.setDefaultTemplate("soap_default", toast),
            ).rejects.toThrow("boom");
            expect(settingsHelpers.showErrorToast).toHaveBeenCalledWith(
                toast,
                "Failed to set default template",
            );
        });
    });
});
