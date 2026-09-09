# Audio gold-set collection protocol (W0.4)

Purpose: a small, consented, reproducible corpus of real Persian medical
dictation clips against which ASR engines can be measured (WER +
script-normalized WER, later BERTScore) via the Wave 2 eval harness
(`scripts/eval_asr.py`).

## Storage (no audio in git)

- `data/` is gitignored. The corpus lives **only** on the evaluation machine:
  `data/eval/` with the layout below. Never commit WAV/MP3 files.
- This document is the tracked, reviewable protocol. A pointer copy may be
  kept at `data/eval/README.md` locally.

```
data/eval/
  manifest.jsonl        # one line per clip (schema below)
  audio/                # 16 kHz mono PCM WAV, one file per clip
  noise/                # MUSAN-style noise clips for synthetic mixes
  synth/                # generated noisy mixes
```

## Consent & privacy (mandatory)

- Collect only from clinicians or actors with written consent for research
  use of a de-identified recording. No patient-identifying information may be
  spoken or on screen in any clip.
- Scrub recordings before storage: remove names, dates, MRNs, addresses.
  Prefer clips where the speaker uses only "بیمار" instead of names.
- Delete raw source files after scrubbing; keep only the final WAV + manifest.

## Clip specification

- Format: 16 kHz, mono, 16-bit PCM WAV.
- Length: 15–120 s.
- Content: real visit dictation in Persian (mixed Persian/English medical
  terms are encouraged — the app's actual code-switching rate is the target).
- Minimum size for a usable baseline: **20–50 real clips** + **10 synthetic
  noisy clips**.

## Synthetic noisy clips

Generate by mixing clean speech with noise (MUSAN or similar):

1. Take a clean clip, add noise at target SNR ∈ {0, 5, 10, 15} dB.
2. Normalize final RMS to −20 dBFS.
3. Name `synth_<seed>_<snr>dB.wav`.

## Gold transcript convention (manual annotation)

For every clip, write a **gold transcript** in the manifest:

- Normalize **before** scoring: Persian digits ۰-۹, YK normalized, case
  folded; keep the spoken form of numbers as spoken (ITN is a separate
  pipeline decision — score raw ASR against the raw gold).
- Punctuation: sentence-ending «.» after each clinical statement; no
  decorative punctuation.
- Code-switched terms keep their script as spoken (`amoxicillin`, `HbA1c`).
- Ambiguous words: annotate the speaker's intended word; if truly
  unrecoverable, mark with `«...»` and exclude the span from WER counting
  (record `excluded_chars` in the manifest).

## `manifest.jsonl` schema

```json
{
  "id": "v001-cardiology",
  "file": "audio/v001-cardiology.wav",
  "kind": "real | synth",
  "synth": {"noise": "noise/mus_babysit_012.wav", "snr_db": 10},
  "duration_s": 42.5,
  "speaker": "A1",
  "specialty": "cardiology",
  "consent": "doc/consent-A1.md#v001",
  "gold": "بیمار مرد پنجاه و دو ساله با درد قفسه سینه مراجعه کرد.",
  "excluded_chars": 0,
  "notes": ""
}
```

## Scoring

- Metrics: WER, script-normalized WER (canonical form above); optional
  BERTScore for code-switching robustness (WER alone under-penalizes
  semantically correct cross-script variants).
- Baselines: commit the baseline JSON next to this document
  (`docs/eval/baselines/`) so regressions are visible without the audio.
