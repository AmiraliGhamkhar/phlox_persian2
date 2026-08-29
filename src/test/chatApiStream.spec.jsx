import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chatApi } from "../utils/api/chatApi";

// chatApi only touches these two helpers for transport; stub them so the
// SSE parser can be exercised deterministically.
vi.mock("../utils/helpers/apiConfig", () => ({
    buildApiUrl: vi.fn(async (path) => `http://local.test${path}`),
}));

vi.mock("../utils/helpers/apiHelpers", () => ({
    handleApiRequest: vi.fn(async ({ apiCall }) => apiCall()),
    universalFetch: vi.fn(),
}));

import { universalFetch } from "../utils/helpers/apiHelpers";

/** Build a fake streaming Response whose body yields the given SSE frames. */
function sseResponse(frames, { delayMs = 0 } = {}) {
    const encoder = new TextEncoder();
    const chunks = frames.map((f) => encoder.encode(f));
    let index = 0;
    return {
        ok: true,
        status: 200,
        body: {
            getReader() {
                return {
                    async read() {
                        if (delayMs) {
                            await new Promise((r) => setTimeout(r, delayMs));
                        }
                        if (index < chunks.length) {
                            return { value: chunks[index++], done: false };
                        }
                        return { value: undefined, done: true };
                    },
                };
            },
        },
    };
}

const frame = (obj) => `data: ${JSON.stringify(obj)}\n\n`;

describe("chatApi.streamMessage", () => {
    beforeEach(() => {
        universalFetch.mockReset();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("yields status/chunk frames and stops cleanly on end", async () => {
        universalFetch.mockResolvedValue(
            sseResponse([
                frame({ type: "start" }),
                frame({ type: "chunk", content: "سلام" }),
                frame({ type: "end" }),
            ]),
        );

        const out = [];
        for await (const c of chatApi.streamMessage([{ role: "user", content: "hi" }])) {
            out.push(c);
        }

        expect(out.map((c) => c.type)).toEqual(["start", "chunk", "end"]);
        // Clean end must NOT append the broken-stream error.
        expect(out.some((c) => c.type === "error")).toBe(false);
    });

    it("splits frames that arrive coalesced in one network chunk", async () => {
        universalFetch.mockResolvedValue(
            sseResponse([
                `${frame({ type: "chunk", content: "a" })}${frame({ type: "chunk", content: "b" })}${frame({ type: "end" })}`,
            ]),
        );

        const types = [];
        for await (const c of chatApi.streamMessage([])) {
            types.push(c.type);
        }
        expect(types).toEqual(["chunk", "chunk", "end"]);
    });

    it("survives malformed frames and reports a broken stream when end is missing", async () => {
        const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
        universalFetch.mockResolvedValue(
            sseResponse([frame({ type: "chunk", content: "partial" }), "data: {not json}\n\n"]),
        );

        const out = [];
        for await (const c of chatApi.streamMessage([])) {
            out.push(c);
        }

        expect(out[0]).toEqual({ type: "chunk", content: "partial" });
        const err = out.find((c) => c.type === "error");
        expect(err).toBeTruthy();
        expect(err.content).toContain("ناقص");
        expect(errorSpy).toHaveBeenCalled();
    });

    it("does not report a broken stream when the user aborted", async () => {
        const controller = new AbortController();
        controller.abort();
        universalFetch.mockResolvedValue(sseResponse([frame({ type: "chunk", content: "x" })]));

        const out = [];
        for await (const c of chatApi.streamMessage([], null, null, controller.signal)) {
            out.push(c);
        }
        expect(out.some((c) => c.type === "error")).toBe(false);
    });

    it("forwards the abort signal to fetch", async () => {
        const controller = new AbortController();
        universalFetch.mockResolvedValue(sseResponse([frame({ type: "end" })]));

        for await (const _ of chatApi.streamMessage([], null, null, controller.signal)) {
            // drain
        }
        expect(universalFetch).toHaveBeenCalledWith(
            "http://local.test/api/chat",
            expect.objectContaining({ signal: controller.signal }),
        );
    });

    it("maps citation arrays from the end event to a context chunk", async () => {
        universalFetch.mockResolvedValue(
            sseResponse([
                frame({
                    type: "end",
                    function_response: { citations: [{ source: "pubmed" }] },
                }),
            ]),
        );

        const out = [];
        for await (const c of chatApi.streamMessage([])) {
            out.push(c);
        }
        const ctx = out.find((c) => c.type === "context");
        expect(ctx).toBeTruthy();
        expect(ctx.content["1"]).toEqual({ source: "pubmed" });
    });
});
