import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { describeLiveError, describeLiveWarning, transcriptionApi } from "./transcriptionApi";

/**
 * Contract tests for the live transcription socket.
 *
 * The important one is the authority downgrade: the recorder uses
 * `authoritative` to decide whether the live text can replace the full
 * recording. A session that dies mid-consult must never report `true`, or the
 * clinician keeps a truncated note and the audio is never re-transcribed.
 */
class FakeWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    static instances: FakeWebSocket[] = [];

    url: string;
    protocol = "";
    readyState = FakeWebSocket.CONNECTING;
    binaryType = "";
    bufferedAmount = 0;
    sent: unknown[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;

    constructor(url: string, _protocols?: string | string[]) {
        this.url = url;
        FakeWebSocket.instances.push(this);
    }

    send(data: unknown) {
        this.sent.push(data);
    }

    close() {
        this.readyState = FakeWebSocket.CLOSED;
        this.onclose?.();
    }

    /** Test helpers. */
    open(protocol = "phlox-live") {
        this.protocol = protocol;
        this.readyState = FakeWebSocket.OPEN;
        this.onopen?.();
    }

    receive(payload: unknown) {
        this.onmessage?.({ data: JSON.stringify(payload) });
    }

    dropUnexpectedly() {
        this.readyState = FakeWebSocket.CLOSED;
        this.onclose?.();
    }

    get jsonFrames(): any[] {
        return this.sent
            .filter((frame) => typeof frame === "string")
            .map((frame) => JSON.parse(frame as string));
    }
}

const lastSocket = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

/** The socket is constructed after two awaited config lookups. */
const waitForSocket = async () => {
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0));
    return lastSocket();
};

beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

const openSession = async (handlers: Record<string, any> = {}) => {
    const promise = transcriptionApi.openLiveTranscription(handlers);
    const socket = await waitForSocket();
    socket.open();
    const session = await promise;
    return { session, socket };
};

describe("openLiveTranscription", () => {
    it("connects with the app subprotocol and reports readiness", async () => {
        const onReady = vi.fn();
        const { socket } = await openSession({ onReady });

        expect(socket.url).toContain("/api/transcribe/live");
        socket.receive({ type: "ready", authoritative: true });
        expect(onReady).toHaveBeenCalledWith({ authoritative: true });
    });

    it("treats a clean session as authoritative on stop", async () => {
        const onFinal = vi.fn();
        const { session, socket } = await openSession({ onFinal });

        socket.receive({ type: "ready", authoritative: true });
        socket.receive({ type: "final", text: "بیمار امروز مراجعه کرد" });
        expect(onFinal).toHaveBeenCalledWith("بیمار امروز مراجعه کرد");

        const pending = session.stop();
        socket.receive({ type: "final", text: "بیمار امروز مراجعه کرد" });
        await expect(pending).resolves.toEqual({
            text: "بیمار امروز مراجعه کرد",
            authoritative: true,
        });
        expect(socket.jsonFrames.at(-1)).toEqual({ type: "stop" });
    });

    it("downgrades authority when the service reports a fatal error", async () => {
        const onError = vi.fn();
        const { session, socket } = await openSession({ onError });

        socket.receive({ type: "ready", authoritative: true });
        socket.receive({ type: "final", text: "ده ثانیه از ویزیت" });
        socket.receive({
            type: "error",
            error_type: "quota_exceeded",
            code: 4005,
            fatal: true,
            retryable: true,
            message: "quota exceeded",
        });

        expect(onError).toHaveBeenCalledTimes(1);
        expect(onError.mock.calls[0][0]).toContain("سقف جلسات همزمان");
        expect(onError.mock.calls[0][1]).toMatchObject({
            errorType: "quota_exceeded",
            retryable: true,
        });

        const pending = session.stop();
        socket.receive({ type: "done" });
        // The partial text is still returned, but it must not be used as the
        // whole transcript: authoritative is false so the batch path runs.
        await expect(pending).resolves.toEqual({
            text: "ده ثانیه از ویزیت",
            authoritative: false,
        });
    });

    it("downgrades authority on a session-ending warning", async () => {
        const onWarning = vi.fn();
        const { session, socket } = await openSession({ onWarning });

        socket.receive({ type: "ready", authoritative: true });
        socket.receive({
            type: "warning",
            warning_type: "duration_limit_exceeded",
            authoritative: false,
            message: "duration limit",
        });
        expect(onWarning.mock.calls[0][0]).toContain("بلندتر از حد مجاز");

        const pending = session.stop();
        socket.receive({ type: "done" });
        await expect(pending).resolves.toMatchObject({ authoritative: false });
    });

    it("downgrades authority and reports an error on an unexpected close", async () => {
        const onError = vi.fn();
        const { session, socket } = await openSession({ onError });

        socket.receive({ type: "ready", authoritative: true });
        socket.receive({ type: "final", text: "بخش اول" });
        socket.dropUnexpectedly();

        expect(onError).toHaveBeenCalledTimes(1);
        const pending = session.stop();
        await expect(pending).resolves.toEqual({
            text: "بخش اول",
            authoritative: false,
        });
    });

    it("settles stop on 'done' without waiting for a trailing final", async () => {
        const { session, socket } = await openSession();
        socket.receive({ type: "ready", authoritative: true });

        const pending = session.stop();
        socket.receive({ type: "done" });
        await expect(pending).resolves.toEqual({ text: "", authoritative: true });
    });

    it("sends a flush frame when recording is paused", async () => {
        const { session, socket } = await openSession();
        session.flush();
        expect(socket.jsonFrames.at(-1)).toEqual({ type: "flush" });
    });

    it("forwards utterance-end and info frames without touching the transcript", async () => {
        const onUtteranceEnd = vi.fn();
        const onFinal = vi.fn();
        const { session, socket } = await openSession({ onUtteranceEnd, onFinal });

        socket.receive({ type: "ready", authoritative: true });
        socket.receive({ type: "utterance_end", forced: true });
        socket.receive({
            type: "info",
            info_type: "concurrent_session_usage",
            usage: 2,
            quota: 5,
        });
        expect(onUtteranceEnd).toHaveBeenCalledWith({ forced: true });
        expect(onFinal).not.toHaveBeenCalled();

        const pending = session.stop();
        socket.receive({ type: "done" });
        await expect(pending).resolves.toMatchObject({ authoritative: true });
    });

    it("skips audio while the socket is already backed up", async () => {
        const { session, socket } = await openSession();
        socket.bufferedAmount = 2_000_000;
        session.sendPcm(new Int16Array(160));
        expect(socket.sent).toHaveLength(0);

        socket.bufferedAmount = 0;
        session.sendPcm(new Int16Array(160));
        expect(socket.sent).toHaveLength(1);
    });

    it("opens in browser mode where no request token is required", async () => {
        const promise = transcriptionApi.openLiveTranscription({});
        const socket = await waitForSocket();
        // No token in Docker mode, so the fail-closed check does not trigger;
        // the open settlement must still resolve.
        socket.open("something-else");
        await expect(promise).resolves.toBeTruthy();
    });
});

describe("live message copy", () => {
    it("maps documented error types to Persian", () => {
        expect(describeLiveError({ error_type: "not_authorised" })).toContain("کلید API");
        expect(describeLiveError({ error_type: "idle_timeout" })).toContain("نبودن صدا");
    });

    it("falls back to the server message for unknown types", () => {
        expect(describeLiveError({ error_type: "brand_new", message: "raw reason" })).toBe(
            "raw reason",
        );
        expect(describeLiveWarning({ message: "raw warning" })).toBe("raw warning");
    });
});
