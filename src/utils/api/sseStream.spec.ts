import { describe, it, expect } from "vitest";
import { parseSSEBlock, readSSEEvents } from "./sseStream";

/** Build a ReadableStreamDefaultReader from an array of string chunks. */
function readerFrom(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
        start(controller) {
            for (const chunk of chunks) {
                controller.enqueue(encoder.encode(chunk));
            }
            controller.close();
        },
    });
    return stream.getReader();
}

async function collect(chunks: string[]): Promise<unknown[]> {
    const out: unknown[] = [];
    for await (const event of readSSEEvents(readerFrom(chunks))) {
        out.push(event);
    }
    return out;
}

describe("parseSSEBlock", () => {
    it("parses a simple data event", () => {
        const events = [...parseSSEBlock('data: {"type": "progress", "value": 5}')];
        expect(events).toEqual([{ type: "progress", value: 5 }]);
    });

    it("skips keepalive comment lines", () => {
        expect([...parseSSEBlock(": keepalive")]).toEqual([]);
    });

    it("swallows unparseable frames (logs instead of throwing)", () => {
        expect([...parseSSEBlock("data: {not json")]).toEqual([]);
    });

    it("joins multi-line data per the SSE spec", () => {
        const events = [...parseSSEBlock('data: {"a":\ndata: 1}')];
        expect(events).toEqual([{ a: 1 }]);
    });
});

describe("readSSEEvents", () => {
    it("parses complete events delivered in one chunk", async () => {
        const events = await collect(['data: {"type": "start"}\n\n']);
        expect(events).toEqual([{ type: "start" }]);
    });

    it("parses multiple events in one chunk", async () => {
        const events = await collect([
            'data: {"type": "start"}\n\ndata: {"type": "progress", "value": 10}\n\n',
        ]);
        expect(events).toEqual([{ type: "start" }, { type: "progress", value: 10 }]);
    });

    it("reassembles an event split across two reads (regression)", async () => {
        // The JSON payload is split mid-frame: a per-read parser drops it.
        const events = await collect([
            'data: {"type": "complete", "size_',
            'mb": 3.2, "filename": "model.gguf"}\n\n',
        ]);
        expect(events).toEqual([
            { type: "complete", size_mb: 3.2, filename: "model.gguf" },
        ]);
    });

    it("reassembles a large result event split across three reads (regression)", async () => {
        const payload = JSON.stringify({
            type: "result",
            data: { reasoning: "x".repeat(500) },
        });
        const full = `data: ${payload}\n\n`;
        const third = Math.floor(full.length / 3);
        const events = await collect([
            full.slice(0, third),
            full.slice(third, third * 2),
            full.slice(third * 2),
        ]);
        expect(events).toEqual([{ type: "result", data: { reasoning: "x".repeat(500) } }]);
    });

    it("handles a boundary falling exactly on the blank-line separator", async () => {
        const events = await collect(['data: {"a": 1}\n', '\ndata: {"b": 2}\n\n']);
        expect(events).toEqual([{ a: 1 }, { b: 2 }]);
    });

    it("flushes a trailing event without a final blank line", async () => {
        const events = await collect(['data: {"type": "final"}\n']);
        expect(events).toEqual([{ type: "final" }]);
    });

    it("ignores keepalives interleaved with real events", async () => {
        const events = await collect([
            ": keepalive\n\ndata: {\"ok\": true}\n\n: keepalive\n\n",
        ]);
        expect(events).toEqual([{ ok: true }]);
    });

    it("keeps multi-byte (Persian) characters intact across chunk boundaries", async () => {
        const full = 'data: {"label": "درمان ملاونوم"}\n\n';
        const bytes = new TextEncoder().encode(full);
        // Split at a byte offset that lands INSIDE a 2-byte Persian char
        // (continuation bytes are 0x80–0xBF).
        let offset = 0;
        for (let i = 0; i < bytes.length; i++) {
            if (bytes[i] >= 0x80 && bytes[i] <= 0xbf) {
                offset = i;
                break;
            }
        }
        expect(offset).toBeGreaterThan(0);
        const stream = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(bytes.slice(0, offset));
                controller.enqueue(bytes.slice(offset));
                controller.close();
            },
        });
        const events: unknown[] = [];
        for await (const event of readSSEEvents(stream.getReader())) {
            events.push(event);
        }
        expect(events).toEqual([{ label: "درمان ملاونوم" }]);
    });
});
