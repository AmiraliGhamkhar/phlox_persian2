import { handleApiRequest, universalFetch } from "../helpers/apiHelpers";
import { buildApiUrl, getApiBaseUrl, getRequestToken } from "../helpers/apiConfig";

/**
 * Persian copy for the realtime error/warning types documented by the ASR
 * service. Keyed by the machine-readable type the server forwards, so a
 * reworded server message cannot break the translation.
 */
const LIVE_ERROR_TEXT_FA: Record<string, string> = {
    not_authorised: "کلید API سرویس گفتار پذیرفته نشد.",
    not_allowed: "این حساب اجازهٔ شروع جلسهٔ پیاده‌سازی زنده را ندارد.",
    quota_exceeded: "سقف جلسات همزمان سرویس گفتار پر است؛ چند لحظه دیگر دوباره تلاش کنید.",
    timelimit_exceeded: "سهمیهٔ زمانی حساب سرویس گفتار به پایان رسیده است.",
    invalid_language: "زبان انتخاب‌شده برای پیاده‌سازی زنده پشتیبانی نمی‌شود.",
    invalid_model: "مدل انتخاب‌شده برای پیاده‌سازی زنده در دسترس نیست.",
    invalid_config: "پیکربندی جلسهٔ زنده توسط سرویس پذیرفته نشد.",
    invalid_audio_type: "قالب صوتی توسط سرویس گفتار پذیرفته نشد.",
    invalid_output_format: "قالب خروجی توسط سرویس گفتار پذیرفته نشد.",
    invalid_message: "پروتکل جلسهٔ زنده با خطا مواجه شد.",
    protocol_error: "پروتکل جلسهٔ زنده با خطا مواجه شد.",
    job_error: "سرویس گفتار نتوانست این جلسه را پردازش کند؛ کمی بعد دوباره تلاش کنید.",
    idle_timeout: "جلسهٔ زنده به دلیل نبودن صدا بسته شد.",
    session_timeout: "جلسهٔ زنده به حداکثر مدت مجاز (۴۸ ساعت) رسید.",
    internal_error: "سرویس گفتار اتصال را بست؛ کمی بعد دوباره تلاش کنید.",
    audio_stalled:
        "سرویس گفتار دریافت صدا را تأیید نکرد؛ برای حفظ بقیهٔ ضبط، جلسهٔ زنده بسته شد.",
    transport_error: "اتصال پیاده‌سازی زنده قطع شد.",
    unknown_error: "سرویس گفتار خطای نامشخصی گزارش کرد.",
};

const LIVE_WARNING_TEXT_FA: Record<string, string> = {
    duration_limit_exceeded:
        "گفتار بلندتر از حد مجاز سرویس زنده بود؛ بقیهٔ صدا پس از توقف پیاده‌سازی می‌شود.",
    idle_timeout: "جلسهٔ زنده به‌زودی به دلیل بی‌فعالیتی بسته می‌شود.",
    session_timeout: "جلسهٔ زنده به حداکثر مدت مجاز نزدیک می‌شود.",
    add_audio_after_eos: "صدای ارسال‌شده پس از پایان جریان نادیده گرفته شد.",
    speaker_id: "شناسایی گوینده با مشکل مواجه شد.",
};

export const describeLiveError = (
    payload: { error_type?: string; message?: string } = {},
): string => {
    const type = payload.error_type ? String(payload.error_type) : "";
    return LIVE_ERROR_TEXT_FA[type] || payload.message || "پیاده‌سازی زنده متوقف شد.";
};

export const describeLiveWarning = (
    payload: { warning_type?: string; message?: string } = {},
): string => {
    const type = payload.warning_type ? String(payload.warning_type) : "";
    return LIVE_WARNING_TEXT_FA[type] || payload.message || "هشدار سرویس پیاده‌سازی زنده.";
};

export interface LiveSessionHandle {
    sendPcm: (samples: Int16Array) => void;
    /** Finalize the pending utterance (called when recording is paused). */
    flush: () => void;
    stop: () => Promise<{ text: string; authoritative: boolean }>;
    close: () => void;
}

export const transcriptionApi = {
    transcribeDictation: async (formData) => {
        return handleApiRequest({
            apiCall: async () => {
                const url = await buildApiUrl(`/api/transcribe/dictate`);
                return universalFetch(url, {
                    method: "POST",
                    body: formData,
                });
            },
            errorMessage: "Error transcribing dictation",
        });
    },

    openLiveTranscription: async ({
        onPartial,
        onFinal,
        onError,
        onWarning,
        onUtteranceEnd,
        onReady,
    }: {
        onPartial?: (text: string) => void;
        onFinal?: (text: string) => void;
        onError?: (message: string, info?: { errorType?: string; retryable?: boolean }) => void;
        onWarning?: (message: string, info?: { warningType?: string }) => void;
        onUtteranceEnd?: (info: { forced: boolean }) => void;
        onReady?: (info: { authoritative: boolean }) => void;
    } = {}): Promise<LiveSessionHandle> => {
        const baseUrl = await getApiBaseUrl();
        const token = await getRequestToken();
        const wsBase = baseUrl
            ? baseUrl.replace(/^http/i, "ws")
            : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
        // Auth token travels in a WebSocket subprotocol, never in the URL:
        // query strings are written to uvicorn access logs and to the desktop
        // app log on disk (A09:2025).
        const subprotocols = token ? ["phlox-live", token] : ["phlox-live"];
        const socket = new WebSocket(`${wsBase}/api/transcribe/live`, subprotocols);

        let lastText = "";
        let authoritative = false;
        let opened = false;
        let stopping = false;
        let settled = false;
        let settleStop: ((result: { text: string; authoritative: boolean }) => void) | null =
            null;

        const result = () => ({ text: lastText, authoritative });

        // One report per session: an in-band Error is usually followed by the
        // socket closing, and the clinician only needs to be told once.
        let reported = false;
        const reportError = (
            message: string,
            info?: { errorType?: string; retryable?: boolean },
        ) => {
            if (reported) return;
            reported = true;
            onError?.(message, info);
        };

        const settle = () => {
            if (!settleStop) return;
            const done = settleStop;
            settleStop = null;
            settled = true;
            done(result());
        };

        /**
         * The live text no longer covers the whole recording, so the caller
         * must not use it as the final transcript: the full audio still has to
         * be batch-transcribed. Without this downgrade a session that dies ten
         * seconds into a three-minute consult silently truncates the note.
         */
        const downgrade = () => {
            authoritative = false;
        };

        socket.binaryType = "arraybuffer";

        socket.onmessage = (event) => {
            if (typeof event.data !== "string") return;
            let payload: any;
            try {
                payload = JSON.parse(event.data);
            } catch {
                return;
            }
            switch (payload?.type) {
                case "ready":
                    authoritative = Boolean(payload.authoritative);
                    onReady?.({ authoritative });
                    return;
                case "partial":
                    lastText = payload.text || lastText;
                    onPartial?.(lastText);
                    return;
                case "final":
                    lastText = payload.text || lastText;
                    onFinal?.(lastText);
                    settle();
                    return;
                case "utterance_end":
                    onUtteranceEnd?.({ forced: Boolean(payload.forced) });
                    return;
                case "warning":
                    // Warnings that end the session early also downgrade the
                    // transcript: the remaining audio is not in the live text.
                    if (payload.authoritative === false) downgrade();
                    onWarning?.(describeLiveWarning(payload), {
                        warningType: payload.warning_type,
                    });
                    return;
                case "error":
                    downgrade();
                    reportError(describeLiveError(payload), {
                        errorType: payload.error_type,
                        retryable: Boolean(payload.retryable),
                    });
                    settle();
                    return;
                case "done":
                    settle();
                    return;
                default:
                    return;
            }
        };

        const sendPcm = (samples: Int16Array) => {
            if (socket.readyState !== WebSocket.OPEN || !samples?.length) return;
            // Speechmatics documents that sending audio faster than the engine
            // reads it can fill TCP buffers and close the socket "with
            // prejudice". Skip frames while the browser is already backed up
            // (~1 MB) rather than overrun the connection.
            if (socket.bufferedAmount > 1_000_000) return;
            // Zero-copy view over the exact byte range. The explicit
            // ArrayBuffer generic satisfies WebSocket.send() under TS 6
            // (ArrayBufferLike is no longer assignable to BufferSource).
            const bytes = new Uint8Array<ArrayBuffer>(
                samples.buffer as ArrayBuffer,
                samples.byteOffset,
                samples.byteLength,
            );
            socket.send(bytes);
        };

        const flush = () => {
            if (socket.readyState !== WebSocket.OPEN) return;
            try {
                socket.send(JSON.stringify({ type: "flush" }));
            } catch {
                // Flushing is an optimization; stop() still finalizes.
            }
        };

        const close = () => {
            try {
                if (
                    socket.readyState === WebSocket.OPEN ||
                    socket.readyState === WebSocket.CONNECTING
                ) {
                    socket.close();
                }
            } catch {
                // already closed
            }
        };

        const stop = () =>
            new Promise<{ text: string; authoritative: boolean }>((resolve) => {
                if (socket.readyState !== WebSocket.OPEN) {
                    resolve(result());
                    return;
                }
                stopping = true;
                const timer = window.setTimeout(() => {
                    settleStop = null;
                    resolve(result());
                    close();
                }, 8000);
                settleStop = (value) => {
                    window.clearTimeout(timer);
                    resolve(value);
                };
                try {
                    socket.send(JSON.stringify({ type: "stop" }));
                } catch {
                    window.clearTimeout(timer);
                    resolve(result());
                }
            });

        // A single onopen handler does both the fail-closed auth check and
        // the open settlement — assigning a second handler here would
        // overwrite the first (the auth check used to be dead code).
        await new Promise<void>((resolve, reject) => {
            const timer = window.setTimeout(() => {
                if (!opened) {
                    close();
                    reject(new Error("Live transcription timed out"));
                }
            }, 8000);
            socket.onopen = () => {
                // Fail closed: an authenticated session must be confirmed by
                // the server via the negotiated subprotocol (token must not
                // echo).
                if (token && socket.protocol !== "phlox-live") {
                    window.clearTimeout(timer);
                    close();
                    reject(new Error("Live transcription authentication failed"));
                    return;
                }
                opened = true;
                window.clearTimeout(timer);
                resolve();
            };
            socket.onerror = () => {
                if (!opened) {
                    window.clearTimeout(timer);
                    reject(new Error("Live transcription unavailable"));
                } else {
                    downgrade();
                    reportError(describeLiveError({ error_type: "transport_error" }));
                }
            };
            socket.onclose = () => {
                // An unexpected close means the live text is incomplete even
                // if the server never got the chance to send an Error frame.
                if (!stopping && !settled) {
                    downgrade();
                    reportError(describeLiveError({ error_type: "transport_error" }));
                }
                settle();
            };
        });

        return { sendPcm, flush, stop, close };
    },
};
