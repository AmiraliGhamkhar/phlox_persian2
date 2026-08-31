import { universalFetch } from "../helpers/apiHelpers";

/**
 * Parse one complete SSE event block ("data: …" lines, blank-line delimited).
 *
 * Yields the parsed JSON payload, or nothing for comments/keepalives
 * (": …") and unparseable frames (logged, not fatal).
 */
export function* parseSSEBlock(block: string): Generator<unknown> {
    let data = "";
    for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue; // comment / keepalive
        if (line.startsWith("data:")) {
            // Per the SSE spec, an event's data is the data-line values
            // joined with newlines.
            const value = line.slice(5).replace(/^ /, "");
            data = data ? `${data}\n${value}` : value;
        }
    }
    if (!data) return;
    try {
        yield JSON.parse(data);
    } catch (error) {
        console.error("Error parsing SSE event:", error, block);
    }
}

/**
 * Read SSE events from a stream reader with cross-chunk buffering.
 *
 * TCP reads do NOT align with event boundaries: a `data:` payload can be
 * split across two reads. Splitting each read independently (and dropping
 * what fails to parse) silently loses such events — e.g. a final
 * "complete"/"result" frame. The trailing fragment is therefore kept in a
 * buffer until the next read (or stream end) completes it.
 */
export async function* readSSEEvents(
    reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<unknown> {
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
            yield* parseSSEBlock(part);
        }
    }

    // Flush a trailing complete event that was not blank-line terminated.
    if (buffer.trim()) {
        yield* parseSSEBlock(buffer);
    }
}

/**
 * POST/GET an SSE endpoint and yield its parsed events (buffered).
 */
export async function* streamSSEEvents(
    url: string,
    options: RequestInit = {},
): AsyncGenerator<unknown> {
    const response = await universalFetch(url, options);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    if (!response.body) {
        throw new Error("SSE response has no body");
    }
    yield* readSSEEvents(response.body.getReader());
}
