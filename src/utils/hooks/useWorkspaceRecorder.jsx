import { useCallback, useEffect, useRef, useState } from "react";
import { toaster } from "@/components/ui/toaster";
import { AudioRecorder } from "../audioRecorder";
import { transcriptionApi } from "../api/transcriptionApi";

export const useWorkspaceRecorder = ({ onTranscript }) => {
    const [isRecording, setIsRecording] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [timer, setTimer] = useState(0);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [liveTranscript, setLiveTranscript] = useState("");
    const [liveError, setLiveError] = useState(null);
    const [liveWarning, setLiveWarning] = useState(null);
    // ASR hygiene metadata from the batch transcription (flags/segments/vad)
    // for the last completed dictation, so the page can amber-flag weak
    // spans and forward them to the report prompt.
    const [transcriptMeta, setTranscriptMeta] = useState(null);

    const audioRecorderRef = useRef(null);
    const liveSessionRef = useRef(null);
    const timerIntervalRef = useRef(null);
    // The ASR service repeats its timeout warnings (15/10/5 minutes out); one
    // toast per distinct message is enough.
    const seenLiveNoticesRef = useRef(new Set());

    const notifyLive = useCallback((title, description, type = "warning") => {
        const key = `${title}::${description}`;
        if (seenLiveNoticesRef.current.has(key)) return;
        seenLiveNoticesRef.current.add(key);
        toaster.create({ title, description, type, duration: 6000 });
    }, []);

    const closeLiveSession = useCallback(() => {
        if (liveSessionRef.current) {
            try {
                liveSessionRef.current.close();
            } catch {
                // already closed
            }
            liveSessionRef.current = null;
        }
    }, []);

    useEffect(() => {
        if (isRecording && !isPaused) {
            timerIntervalRef.current = setInterval(() => {
                setTimer((prev) => prev + 1);
            }, 1000);
        } else {
            clearInterval(timerIntervalRef.current);
        }
        return () => clearInterval(timerIntervalRef.current);
    }, [isRecording, isPaused]);

    useEffect(() => {
        return () => {
            closeLiveSession();
            if (audioRecorderRef.current) {
                audioRecorderRef.current.stop().catch(() => {});
            }
        };
    }, [closeLiveSession]);

    const transcribeBlob = useCallback(
        async (blob, liveResult = null) => {
            if (liveResult?.authoritative && liveResult?.text) {
                onTranscript?.(liveResult.text);
                return liveResult.text;
            }
            if (!blob) return "";
            setIsTranscribing(true);
            try {
                const formData = new FormData();
                formData.append("file", blob, "recording.wav");
                const data = await transcriptionApi.transcribeDictation(formData);
                const text = data?.transcription || data?.rawTranscription || "";
                setTranscriptMeta(
                    data
                        ? {
                              flags: data.flags || [],
                              segments: data.segments || [],
                              vad: data.vad || {},
                          }
                        : null,
                );
                if (text) onTranscript?.(text);
                return text;
            } finally {
                setIsTranscribing(false);
            }
        },
        [onTranscript],
    );

    const startRecording = useCallback(async () => {
        try {
            const recorder = new AudioRecorder();
            setLiveTranscript("");
            setLiveError(null);
            setLiveWarning(null);
            setTranscriptMeta(null);
            seenLiveNoticesRef.current = new Set();
            try {
                const session = await transcriptionApi.openLiveTranscription({
                    onPartial: (text) => setLiveTranscript(text || ""),
                    onFinal: (text) => setLiveTranscript(text || ""),
                    onError: (message) => {
                        // The recording itself continues; only the live preview
                        // is gone, and the full audio is transcribed on stop.
                        setLiveError(message);
                        notifyLive("پیاده‌سازی زنده متوقف شد", message, "error");
                    },
                    onWarning: (message) => {
                        setLiveWarning(message);
                        notifyLive("هشدار سرویس پیاده‌سازی", message);
                    },
                });
                liveSessionRef.current = session;
                recorder.onPcm = (samples) => session.sendPcm(samples);
            } catch (error) {
                setLiveError(error?.message || String(error));
            }
            await recorder.start();
            audioRecorderRef.current = recorder;
            setIsRecording(true);
            setIsPaused(false);
            setTimer(0);
        } catch (error) {
            console.error("Error starting recording:", error);
            closeLiveSession();
            toaster.create({
                title: "دسترسی به میکروفون ممکن نبود",
                description: "لطفاً مجوزهای مرورگر برای میکروفون را بررسی کنید.",
                type: "warning",
                duration: 6000,
            });
        }
    }, [closeLiveSession, notifyLive]);

    const pauseRecording = useCallback(() => {
        audioRecorderRef.current?.pause();
        // Finalize the pending utterance so the transcript is not left
        // mid-sentence for the whole pause.
        liveSessionRef.current?.flush?.();
        setIsPaused(true);
    }, []);

    const resumeRecording = useCallback(() => {
        audioRecorderRef.current?.resume();
        setIsPaused(false);
    }, []);

    const stopAndTranscribe = useCallback(async () => {
        if (!isRecording || !audioRecorderRef.current) return "";
        const recorder = audioRecorderRef.current;
        audioRecorderRef.current = null;
        setIsRecording(false);
        setIsPaused(false);
        let liveResult = { text: "", authoritative: false };
        if (liveSessionRef.current) {
            try {
                liveResult = (await liveSessionRef.current.stop()) || liveResult;
            } catch {
                // overlay-only; batch transcription still runs
            }
            closeLiveSession();
        }
        let blob = null;
        try {
            blob = await recorder.stop();
        } catch (error) {
            console.error("Failed to finalise recording:", error);
        }
        const preview = liveResult?.text || liveTranscript;
        if (preview) onTranscript?.(preview);
        try {
            return await transcribeBlob(blob, liveResult);
        } catch (error) {
            toaster.create({
                title: "پیاده‌سازی ناموفق بود",
                description: error?.message || "لطفاً دوباره تلاش کنید.",
                type: "error",
                duration: 6000,
            });
            return preview || "";
        }
    }, [
        isRecording,
        closeLiveSession,
        liveTranscript,
        onTranscript,
        transcribeBlob,
    ]);

    const resetRecording = useCallback(() => {
        if (isRecording && audioRecorderRef.current) {
            audioRecorderRef.current.stop().catch(() => {});
            audioRecorderRef.current = null;
        }
        closeLiveSession();
        setIsRecording(false);
        setIsPaused(false);
        setTimer(0);
        setLiveTranscript("");
        setLiveError(null);
        setLiveWarning(null);
        setTranscriptMeta(null);
    }, [isRecording, closeLiveSession]);

    return {
        isRecording,
        isPaused,
        timer,
        isTranscribing,
        liveTranscript,
        liveError,
        liveWarning,
        transcriptMeta,
        startRecording,
        pauseRecording,
        resumeRecording,
        stopAndTranscribe,
        resetRecording,
    };
};
