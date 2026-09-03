# ASR model benchmark (plan ref A7)

Compare candidate speech-to-text engines on the *same* audio and references,
then score with `server/bench/asr_scorer.py` (WER / CER / Missed-Entity
Rate). No training happens here — this is an evaluation matrix only.

## Layout

```text
bench-run/
  clips/            fa-reflux-001.wav en-gerd-004.wav ...   # 16 k mono wav
  refs/             fa-reflux-001.txt en-gerd-004.txt ...   # gold text
  hyp_whisper-large-v3/    <same ids>.txt
  hyp_faster-whisper/      <same ids>.txt
  ...
```

References can come from the precision fixtures instead of files:
`server/bench/fixtures/precision_fa_en.jsonl` carries a `transcript` per
fixture id (`--from-fixtures`).

## Producing hypotheses (command matrix)

| Model | How to transcribe a clip → text |
| --- | --- |
| whisper.cpp (app's local server) | `curl -s http://127.0.0.1:5001/v1/audio/transcriptions -F file=@clip.wav -F model=whisper-1 -F response_format=verbose_json -F temperature=0 -F prompt="$BIAS" \| jq -r '.segments[].text' > out.txt` |
| faster-whisper (GPU box) | `python - <<'PY' … WhisperModel("large-v3", compute_type="float16"); model.transcribe(clip, beam_size=1, word_timestamps=False, initial_prompt=BIAS) …` write `segments.text` joined |
| openai/whisper (reference impl) | `whisper clip.wav --model large-v3 --language fa --output_format txt --output_dir hyp_whisper-openai --word_timestamps False` |
| Shenava fa (local) | same OpenAI-compatible endpoint as whisper.cpp after installing the Shenava model via the app's model manager |
| Parakeet (local EN) | `nemo_asr` transcription script, or the app path; write plain text per clip |
| Speechmatics Batch | upload job with `operations:[{"op":"insert","path":"/transcription_config","value":{"language":"fa","custom_vocabulary":[…terms…]}}]`, then `jq -r '.results.transcript'` |
| Fireworks whisper-turbo | batch file API, `response_format=verbose_json`, join segment texts |

Guidelines for a fair matrix (all follow the precision plan):

* always greedy: `beam_size = 1` (measured: lowest hallucination verbosity);
* trim leading/trailing silence first (or record raw clips and let the app
  path's VAD do it — then measure both);
* keep the whisper `prompt`/`initial_prompt` biasing identical across models
  or absent for all — never compare a biased model against unbiased ones;
* Persian text: the scorer folds digits/ZWNJ/script variants itself, so
  models may output either Unicode flavor.

## Scoring

```bash
python -m server.bench.asr_scorer --refs bench-run/refs \
    --hyp bench-run/hyp_whisper-large-v3 bench-run/hyp_faster-whisper \
    --json bench-run/report.json

# gate mode (e.g. nightly): fail if a candidate regresses
python -m server.bench.asr_scorer --from-fixtures server/bench/fixtures/precision_fa_en.jsonl \
    --hyp bench-run/hyp_candidate --max-wer 0.25 --max-mer 0.10
```

(`scripts/bench_asr_models.py` is a compatibility shim for the same tool.)

`MER` counts reference numeric facts (doses, values) and salient Latin terms
that are missing or altered in the hypothesis — the clinical-error proxy the
literature reports (missed medication entities drive most clinically
significant ASR errors). Per-file output lists the exact missed entities.
