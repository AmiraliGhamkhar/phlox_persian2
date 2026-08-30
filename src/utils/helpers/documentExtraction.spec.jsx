import { describe, it, expect, vi, beforeEach } from "vitest";

import {
    extractFromFile,
    getDocumentProcessingPreferences,
} from "./documentExtraction";
import { settingsApi } from "../api/settingsApi";
import { chatApi } from "../api/chatApi";
import * as visionHelpers from "./pdfVisionHelpers";

describe("getDocumentProcessingPreferences", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("uses the configured mode and legacy vision flag when capability is unavailable", async () => {
        vi.spyOn(settingsApi, "fetchConfig").mockResolvedValue({
            DOCUMENT_IMAGE_PROCESSING_MODE: "vision",
            VISION_MODEL_CAPABLE: true,
        });
        vi.spyOn(chatApi, "getCurrentVisionCapability").mockRejectedValue(
            new Error("offline"),
        );
        const prefs = await getDocumentProcessingPreferences();
        expect(prefs).toEqual({ mode: "vision", visionCapable: true });
    });

    it("lets a live capability result override the legacy flag", async () => {
        vi.spyOn(settingsApi, "fetchConfig").mockResolvedValue({
            DOCUMENT_IMAGE_PROCESSING_MODE: "auto",
            VISION_MODEL_CAPABLE: true,
        });
        vi.spyOn(chatApi, "getCurrentVisionCapability").mockResolvedValue({
            vision_capable: false,
        });
        const prefs = await getDocumentProcessingPreferences();
        expect(prefs).toEqual({ mode: "auto", visionCapable: false });
    });

    it("normalizes unknown modes to auto and defaults safely on config errors", async () => {
        vi.spyOn(settingsApi, "fetchConfig").mockResolvedValue({
            DOCUMENT_IMAGE_PROCESSING_MODE: "sideways",
        });
        vi.spyOn(chatApi, "getCurrentVisionCapability").mockRejectedValue(
            new Error("offline"),
        );
        const prefs = await getDocumentProcessingPreferences();
        expect(prefs).toEqual({ mode: "auto", visionCapable: false });
    });
});

describe("extractFromFile", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("routes text files through fromText", async () => {
        const api = {
            fromText: vi.fn().mockResolvedValue({ ok: true }),
            legacyFile: vi.fn(),
            visual: vi.fn(),
        };
        const file = new File(["hello world"], "note.txt", {
            type: "text/plain",
        });
        await extractFromFile(file, api, { name: "Ada" });
        expect(api.fromText).toHaveBeenCalledWith({
            extracted_text: "hello world",
            name: "Ada",
            gender: null,
            dob: null,
            templateKey: null,
        });
        expect(api.legacyFile).not.toHaveBeenCalled();
        expect(api.visual).not.toHaveBeenCalled();
    });

    it("routes non-PDF, non-text, non-image files through legacyFile", async () => {
        const api = {
            fromText: vi.fn(),
            legacyFile: vi.fn().mockResolvedValue({ ok: true }),
            visual: vi.fn(),
        };
        const file = new File(["data"], "archive.docx", {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        });
        await extractFromFile(file, api);
        expect(api.legacyFile).toHaveBeenCalledTimes(1);
    });

    it("uses the extracted text layer directly when it is usable", async () => {
        vi.spyOn(settingsApi, "fetchConfig").mockResolvedValue({});
        vi.spyOn(chatApi, "getCurrentVisionCapability").mockResolvedValue({
            vision_capable: true,
        });
        vi.spyOn(visionHelpers, "extractPdfText").mockResolvedValue({
            text: "usable text layer",
            quality: { usable: true },
        });
        const api = {
            fromText: vi.fn().mockResolvedValue({ ok: true }),
            legacyFile: vi.fn(),
            visual: vi.fn(),
        };
        const file = new File(["pdf bytes"], "doc.pdf", {
            type: "application/pdf",
        });
        await extractFromFile(file, api);
        expect(api.fromText).toHaveBeenCalledWith(
            expect.objectContaining({ extracted_text: "usable text layer" }),
        );
        expect(api.visual).not.toHaveBeenCalled();
    });
});
