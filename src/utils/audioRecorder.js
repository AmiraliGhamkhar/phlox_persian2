// Audio capture via WebAudio API.
//
// Prefers AudioWorklet (the ScriptProcessorNode path is deprecated and runs
// audio on the main thread). Samples are resampled to 16 kHz and converted
// to Int16 incrementally per callback, so a long dictation session keeps at
// most ~2 bytes/sample in memory instead of native-rate Float32 (~4x more,
// at typically 48 kHz).

export const TARGET_SAMPLE_RATE = 16000;
const PROCESSOR_BUFFER_SIZE = 4096;
const WORKLET_PROCESSOR_NAME = "phlox-capture";

// The worklet module is inlined through a Blob URL so it loads identically
// in the browser dev server and inside the Tauri webview, with no extra
// asset plumbing.
const WORKLET_SOURCE = `
class PhloxCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      const copy = new Float32Array(channel);
      this.port.postMessage(copy, [copy.buffer]);
    }
    return true;
  }
}
registerProcessor(${JSON.stringify(WORKLET_PROCESSOR_NAME)}, PhloxCaptureProcessor);
`;

/**
 * Streaming linear resampler.
 *
 * Interpolates chunk by chunk while carrying fractional position and the
 * last sample across chunk boundaries, so processing N chunks yields the
 * same signal as resampling the concatenated input in one pass (up to the
 * one-sample tail held back for interpolation).
 */
export class StreamingResampler {
    constructor(inputRate, outputRate) {
        this.step = inputRate / outputRate; // input samples per output sample
        this.pos = 0; // next output position, measured from `prev`
        this.prev = 0; // last input sample seen
        this.primed = false;
    }

    /** Resample one Float32Array chunk; returns a Float32Array. */
    process(input) {
        const n = input.length;
        if (n === 0) return new Float32Array(0);

        // Identity rate: nothing to interpolate, no sample held back.
        if (this.step === 1) return Float32Array.from(input);

        if (!this.primed) {
            this.prev = input[0];
            // First output lands exactly on input[0] (position 0), so the
            // streamed positions k*step line up with a single-pass resample.
            this.pos = 1;
            this.primed = true;
        }

        const out = [];
        let p = this.pos;
        // Emit outputs whose interpolation window stays inside this chunk;
        // anything needing the *next* chunk's first sample is deferred.
        while (p - 1 <= n - 2 + 1e-9) {
            const abs = p - 1; // absolute input index (-1 == prev)
            let sample;
            if (abs < 0) {
                sample = this.prev + (input[0] - this.prev) * (abs + 1);
            } else {
                const i = Math.floor(abs);
                const frac = abs - i;
                sample = input[i] + (input[i + 1] - input[i]) * frac;
            }
            out.push(sample);
            p += this.step;
        }

        // Re-base the remaining position against the new tail sample: the
        // old absolute index (p - 1) minus the chunk length n is the new
        // absolute index, and pos measures one above that.
        this.pos = p - n;
        this.prev = input[n - 1];
        return Float32Array.from(out);
    }
}

export class AudioRecorder {
    constructor() {
        this.audioContext = null;
        this.source = null;
        this.workletNode = null; // AudioWorklet path
        this.processor = null; // ScriptProcessor fallback path
        this.stream = null;
        this.chunks = []; // Int16Array chunks at TARGET_SAMPLE_RATE
        this.isRecording = false;
        this.isPaused = false;
        this.onPcm = null;
        this.resampler = null;
    }

    async start() {
        if (this.isRecording) {
            throw new Error("Already recording");
        }

        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
            },
        });

        this.audioContext = new AudioContext();
        this.source = this.audioContext.createMediaStreamSource(this.stream);
        this.resampler = new StreamingResampler(
            this.audioContext.sampleRate,
            TARGET_SAMPLE_RATE,
        );
        this.chunks = [];

        let workletReady = false;
        if (this.audioContext.audioWorklet) {
            try {
                const moduleUrl = URL.createObjectURL(
                    new Blob([WORKLET_SOURCE], { type: "application/javascript" }),
                );
                try {
                    await this.audioContext.audioWorklet.addModule(moduleUrl);
                } finally {
                    URL.revokeObjectURL(moduleUrl);
                }
                this.workletNode = new AudioWorkletNode(
                    this.audioContext,
                    WORKLET_PROCESSOR_NAME,
                );
                this.workletNode.port.onmessage = (event) =>
                    this.handleSamples(event.data);
                this.source.connect(this.workletNode);
                workletReady = true;
            } catch (error) {
                // Non-secure contexts or older webviews: fall back below.
                console.warn("AudioWorklet unavailable, falling back:", error);
                if (this.workletNode) {
                    try {
                        this.workletNode.disconnect();
                    } catch {
                        // already disconnected
                    }
                    this.workletNode = null;
                }
            }
        }

        if (!workletReady) {
            // Deprecated but universally supported fallback.
            this.processor = this.audioContext.createScriptProcessor(
                PROCESSOR_BUFFER_SIZE,
                1,
                1,
            );
            this.processor.onaudioprocess = (event) => {
                this.handleSamples(
                    new Float32Array(event.inputBuffer.getChannelData(0)),
                );
            };
            this.source.connect(this.processor);
            this.processor.connect(this.audioContext.destination);
        }

        this.isRecording = true;
        this.isPaused = false;
    }

    /** Resample one native-rate chunk to 16 kHz Int16 and store/stream it. */
    handleSamples(float32) {
        if (!this.isRecording || this.isPaused) return;
        const resampled = this.resampler.process(float32);
        if (!resampled.length) return;
        const pcm = floatToInt16(resampled);
        this.chunks.push(pcm);
        if (this.onPcm) {
            this.onPcm(pcm);
        }
    }

    pause() {
        if (!this.isRecording) return;
        this.isPaused = true;
    }

    resume() {
        this.isPaused = false;
    }

    async stop() {
        if (!this.isRecording) {
            throw new Error("Not recording");
        }
        this.isRecording = false;
        this.isPaused = false;

        // Tear down the WebAudio graph before we touch chunks.
        if (this.workletNode) {
            this.workletNode.port.onmessage = null;
            try {
                this.source.disconnect();
                this.workletNode.disconnect();
            } catch {
                // disconnect() throws if already disconnected — ignore.
            }
            this.workletNode = null;
        }
        if (this.processor) {
            this.processor.onaudioprocess = null;
            try {
                this.source.disconnect();
                this.processor.disconnect();
            } catch {
                // disconnect() throws if already disconnected — ignore.
            }
            this.processor = null;
        }
        this.stream.getTracks().forEach((track) => track.stop());

        await this.audioContext.close();

        const pcm = concatInt16(this.chunks);
        this.chunks = [];

        const wav = encodeWavInt16(pcm, TARGET_SAMPLE_RATE);
        return new Blob([wav], { type: "audio/wav" });
    }
}

export function floatToInt16(samples) {
    const output = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return output;
}

function concatInt16(chunks) {
    const totalLength = chunks.reduce((acc, c) => acc + c.length, 0);
    const flat = new Int16Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
        flat.set(chunk, offset);
        offset += chunk.length;
    }
    return flat;
}

/// Write a standard 16-bit PCM WAV header around Int16 samples.
export function encodeWavInt16(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    const writeString = (offset, str) => {
        for (let i = 0; i < str.length; i++) {
            view.setUint8(offset + i, str.charCodeAt(i));
        }
    };

    // RIFF chunk
    writeString(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, "WAVE");

    // fmt subchunk
    writeString(12, "fmt ");
    view.setUint32(16, 16, true); // subchunk size
    view.setUint16(20, 1, true); // audio format = PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // byte rate
    view.setUint16(32, 2, true); // block align
    view.setUint16(34, 16, true); // bits per sample

    // data subchunk
    writeString(36, "data");
    view.setUint32(40, samples.length * 2, true);

    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
        view.setInt16(offset, samples[i], true);
        offset += 2;
    }

    return buffer;
}
