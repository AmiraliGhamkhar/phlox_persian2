import { describe, expect, it } from "vitest";
import {
    StreamingResampler,
    encodeWavInt16,
    floatToInt16,
} from "../utils/audioRecorder";

const singlePassResample = (input, fromRate, toRate) => {
    if (fromRate === toRate) return Float32Array.from(input);
    const ratio = toRate / fromRate;
    const outputLength = Math.floor(input.length * ratio);
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i++) {
        const srcIdx = i / ratio;
        const idx0 = Math.floor(srcIdx);
        const idx1 = Math.min(idx0 + 1, input.length - 1);
        const frac = srcIdx - idx0;
        output[i] = input[idx0] * (1 - frac) + input[idx1] * frac;
    }
    return output;
};

describe("StreamingResampler", () => {
    it("passes samples through unchanged at equal rates", () => {
        const resampler = new StreamingResampler(16000, 16000);
        const input = Float32Array.from([0.1, -0.5, 0.25, 0.75]);
        const out = resampler.process(input);
        expect(Array.from(out)).toEqual(Array.from(input));
    });

    it("outputs roughly input/ratio samples per chunk (48k -> 16k)", () => {
        const resampler = new StreamingResampler(48000, 16000);
        const chunk = new Float32Array(4096).fill(0.5);
        const out = resampler.process(chunk);
        // ratio 3: expect ~1365 outputs, tolerance for boundary handling
        expect(out.length).toBeGreaterThan(1300);
        expect(out.length).toBeLessThanOrEqual(1366);
        for (const sample of out) {
            expect(sample).toBeCloseTo(0.5, 5);
        }
    });

    it("matches a single-pass resample across chunk boundaries", () => {
        const fromRate = 48000;
        const toRate = 16000;
        // Deterministic non-trivial signal (two sine components).
        const total = 9000;
        const signal = new Float32Array(total);
        for (let i = 0; i < total; i++) {
            signal[i] =
                0.6 * Math.sin((2 * Math.PI * 440 * i) / fromRate) +
                0.3 * Math.sin((2 * Math.PI * 1000 * i) / fromRate);
        }

        const chunkSize = 4096;
        const resampler = new StreamingResampler(fromRate, toRate);
        const streamed = [];
        for (let start = 0; start < total; start += chunkSize) {
            const chunk = signal.slice(start, start + chunkSize);
            streamed.push(...resampler.process(chunk));
        }

        const reference = singlePassResample(signal, fromRate, toRate);
        // The stream holds back up to ~step samples at the very end for
        // interpolation; everything before that must line up closely.
        const comparable = Math.min(streamed.length, reference.length);
        expect(comparable).toBeGreaterThan(reference.length - 4);
        let maxError = 0;
        for (let i = 0; i < comparable; i++) {
            maxError = Math.max(maxError, Math.abs(streamed[i] - reference[i]));
        }
        expect(maxError).toBeLessThan(1e-4);
    });

    it("handles empty chunks without corrupting state", () => {
        const resampler = new StreamingResampler(48000, 16000);
        expect(resampler.process(new Float32Array(0)).length).toBe(0);
        const out = resampler.process(Float32Array.from([0.2, 0.4, 0.6, 0.8]));
        expect(out.length).toBeGreaterThan(0);
    });
});

describe("PCM helpers", () => {
    it("floatToInt16 clamps and maps the [-1, 1] range", () => {
        const out = floatToInt16(Float32Array.from([-2, -1, 0, 1, 2]));
        expect(out[0]).toBe(-32768);
        expect(out[1]).toBe(-32768);
        expect(out[2]).toBe(0);
        expect(out[3]).toBe(32767);
        expect(out[4]).toBe(32767);
    });

    it("encodeWavInt16 writes a valid mono 16-bit WAV header", () => {
        const samples = Int16Array.from([0, 100, -100]);
        const buffer = encodeWavInt16(samples, 16000);
        const view = new DataView(buffer);
        const tag = (offset) =>
            String.fromCharCode(
                view.getUint8(offset),
                view.getUint8(offset + 1),
                view.getUint8(offset + 2),
                view.getUint8(offset + 3),
            );
        expect(tag(0)).toBe("RIFF");
        expect(tag(8)).toBe("WAVE");
        expect(view.getUint16(22, true)).toBe(1); // mono
        expect(view.getUint32(24, true)).toBe(16000);
        expect(view.getUint16(34, true)).toBe(16); // bits per sample
        expect(view.getUint32(40, true)).toBe(samples.length * 2);
        expect(view.getInt16(48, true)).toBe(-100); // third sample (44 + 2*2)
        expect(buffer.byteLength).toBe(44 + samples.length * 2);
    });
});
