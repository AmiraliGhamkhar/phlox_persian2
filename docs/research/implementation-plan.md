# Phlox Accuracy Improvements — Implementation Plan

**Date:** 2026-09-09 · **Companion doc:** `docs/research/persian-medical-accuracy-research.md`
**Branch:** `arena/01a085bf-phlox-persian2`
**Goal:** reduce hallucination and improve medical accuracy (LLM correction), ASR quality, RTL handling, and audio preprocessing — without changing the app's architecture, provider model, or security posture.

## Conventions used in this plan

- **Effort:** S = ≤ 0.5 dev-day · M = 1–2 dev-days · L = 3–5 dev-days (single developer, including tests)
- All new server dependencies go in **optional extras** (pattern: `asr = [numpy, onnxruntime]`) so the online/Docker-light builds stay unchanged; every feature must **fail open** (missing extra ⇒ current behavior + a logged debug line).
- All new user-facing text is Persian. All new env vars are documented in `.env.example` and clamped/validated in `server/api/config/validation.py` where relevant.
- CI gates that must keep passing: `ruff`, `ty`, `pytest` (server), `vitest`/lint/typecheck (web), nightly offline bench (`server/bench/run_bench.py --mode offline`), CodeQL.
- Every wave ends with the gold-set score run (W0.3) so each change is measured, not just tested.

---

## Key codebase facts the plan builds on

1. **Deterministic verification guards already exist** — `server/bench/guards.py`:
   - `detect_number_drift(source, generated)` — numbers in output not in input (digit regex, `.`/`,` normalized).
   - `detect_negation_flip(source, generated)` — global polarity pairs (ندارد→دارد, نیست→است, نمی‌کند→می‌کند).
   - `detect_fabrication(source, generated)` — generated sentences with <25% token overlap with source.
   - Used **only** by the nightly offline bench and `tests/test_bench_offline.py` — **not** by the live report path.
2. **Report path:** `POST /api/workspace/report` → `generate_clinical_report()` (`server/nlp_tools/report.py`) → single LLM call (temp 0, seed 0) with `REPORT_SYSTEM_PROMPT` + `terminology_reference_block()` → `ClinicalReport` (Pydantic, `extra="forbid"`) + `repair_json`.
3. **ASR path:** `POST /api/transcribe/dictate` → `transcribe_audio()` → `prepare_audio()` (transcode→energy-VAD trim) → engine → `build_hygiene_result()` returns `segments`/`flags`/`vad`, but `/dictate` **discards** them (returns only `transcription` + duration).
4. **Dictionary:** 5,891 entries, no provenance fields; `terms_for_context()` uses raw substring containment (unlike `search()` which has short-term guards).
5. **Test layout:** `server/tests/` (pytest + pytest-asyncio), gold text fixtures inline in `tests/test_precision_phase1.py`; frontend `vitest`.
6. **Git:** `data/` is gitignored (good for gold audio); `server/data/terms/*.json` explicitly tracked.
7. **Optional-dep pattern:** `server/pyproject.toml` `[project.optional-dependencies] asr = [numpy, onnxruntime]`; ONNX runtimes (Shenava/Parakeet) are in-process; model downloads managed in `server/utils/whisper_models.py`.

---

# Wave 0 — Measurement foundation (do first; everything else is scored against it)

**Why first:** prompt/model/ASR changes without a gold set are unmeasured. This wave also consolidates the existing bench guards into a production module so later waves have one source of truth.

| ID | Task | Files | Effort |
|----|------|-------|--------|
| W0.1 | **Create production verification module** `server/nlp_tools/verification.py`. Move the three guard functions here (keep `server/bench/guards.py` as a thin re-export so the nightly gate and its tests keep working unchanged). Extend: (a) `normalize_value()` — unify Persian ۰-۹ / Arabic-Indic ٠-٩ / ASCII digits and `،`/`.` before number comparison; (b) unit-aware extraction — number+unit pairs (mg, ml, %،٪, روز, ساعت, bar, mmHg, mmol/L, µg, etc.) compared as pairs, so "7.2 mg" vs "7.2 g" is caught; (c) `extract_clinical_terms(text)` — dictionary-grounded extraction (drugs/conditions via ZWNJ-stripped word-boundary matching, reusing `medical_dictionary._normalise`) returning terms present in generated-but-not-source; (d) **context-aware negation check** — instead of global pairs, for each negated predicate in source (e.g. "درد شکم ندارد") check the *same predicate* in generated is not affirmed; keep the global check as a secondary signal. Output: `VerificationResult` dataclass: `findings: list[Finding]` with `kind` (number_drift / negation_flip / ungrounded_term / low_overlap_sentence), `severity` (warn), `source_span`, `detail` (Persian, human-readable). Design rule: **conservative — flag, never edit, never block.** | new `server/nlp_tools/verification.py`; edit `server/bench/guards.py`, `server/bench/run_bench.py` (re-export), `server/tests/test_bench_offline.py` (import path) | M |
| W0.2 | **Gold text set** (committed, text-only): `server/tests/gold/note_pairs.jsonl` — 25–40 Persian clinical transcript→gold-note pairs covering: drug+dosage, lab values (HbA1c, CBC), negations ("ندارد/نبود"), garbled/unclear spans, mixed fa/en (amoxicillin 500 mg), age/sex, bulleted lists, spoken numbers ("پانصد میلی‌گرم"). Each row: `{id, transcript, gold_note, notes}`. Hand-authored with domain review (clinician + linguist), version-controlled like terms. | new `server/tests/gold/note_pairs.jsonl` + `server/tests/test_gold_set.py` (schema/validity tests: no empty, Persian present, IDs unique) | M |
| W0.3 | **Scoring script** `server/bench/score_notes.py`: input = (transcript, note) pairs (file or replay of gold set), runs the W0.1 verification module, prints/JSON-dumps per-pair findings + aggregate precision/recall of planted-error detection on the gold set (gold notes must produce **zero** findings; a companion `note_pairs_with_planted_errors.jsonl` where 3–4 clinical facts are deliberately corrupted must be **caught**). Exit code 1 on regression vs a committed baseline `server/tests/gold/baseline.json`. Add to nightly workflow alongside the offline bench. | new `server/bench/score_notes.py`, `server/tests/gold/note_pairs_with_planted_errors.jsonl`, `server/tests/gold/baseline.json`, edit `.github/workflows/nightly.yml` | M |
| W0.4 | **Gold audio set (outside git):** `data/eval/README.md` (already gitignored) documenting the collection protocol (consent, 16 kHz mono WAV, ≥20–50 clips of real visits + 10 synthetic noisy clips generated by mixing clean speech with MUSAN noise), plus the gold transcript convention. No audio in git. | new `data/eval/README.md` | S |

**Acceptance (Wave 0):**
- `server/tests` green; nightly offline bench green (unchanged behavior via re-export).
- `uv run python -m server.bench.score_notes --gold` runs on the committed gold set, zero findings on gold notes, catches all planted errors; baseline committed.
- Negation context-awareness proven by tests: "درد قفسه سینه ندارد، اما درد شکم دارد" in source + note mentioning "درد شکم دارد" must **not** flag (the classic false positive of the global check).

---

# Wave 1 — P0: verification + uncertainty in the live path (highest ROI)

**Goal:** the three P0 items — the LLM is checked after generation, and it is told which spans are uncertain before generation.

| ID | Task | Files | Effort |
|----|------|-------|--------|
| W1.1 | **Wire verification into report generation.** In `generate_clinical_report()`: after `ClinicalReport.model_validate_json`, build `full_note`, then run `verify_note(transcript, full_note_and_sections)`. Store `result["warnings"] = [f.model_dump() for f in verification.findings]`. Log (never raise) when findings exist. | `server/nlp_tools/report.py` | S |
| W1.2 | **API + schema:** `GenerateReportResponse.warnings: list[dict] = []`; no other contract change (additive, backward-compatible). | `server/schemas/workspace.py`, `server/api/workspace.py` (pass-through), `server/tests/test_workspace.py` (mock LLM returning a drifted note → warnings present) | S |
| W1.3 | **UI surfacing.** In `WorkspacePage.jsx`: when `data.warnings?.length`, render an amber review banner under the report: "۲ مورد نیاز به بررسی دارد" + one Persian line per finding (e.g. "عدد ۸٫۱ در یادداشت هست ولی در متن پیاده‌سازی نیامده است"). Copy button unchanged. Add/extend vitest snapshot. | `src/pages/WorkspacePage.jsx`, `src/utils/api/workspaceApi.ts`, `src/test/workspace.spec.jsx`, `src/i18n/fa.js` | M |
| W1.4 | **Abstention prompt rule.** Append to `REPORT_SYSTEM_PROMPT` (Persian): garbled/unclear spans must be reproduced verbatim (or marked), never "repaired" into a plausible value; if a number/dose is unclear, keep the unclear form. Add a prompt-regression test asserting the key rule substrings exist (guards against silent prompt edits). | `server/nlp_tools/report.py`, new `server/tests/test_prompt_guardrails.py` | S |
| W1.5 | **Propagate ASR confidence end-to-end.** (a) `/dictate` response: add `flags`, `segments`, `vad` (already computed in `transcribe_audio`, currently discarded). (b) `useWorkspaceRecorder` stores them alongside the transcript; UI renders subtle badges on flagged spans (list of flagged segments with reason; per-line amber underline where segment text is locatable). (c) `GenerateReportRequest` gains optional `transcript_flags: list[dict]` and `low_confidence_spans: list[str]`. (d) `build_report_system_prompt()` appends a block: "این قطعات اطمینان پایینی دارند: … — محتوایشان را به‌عنوان حقیقت استوار ننویسید؛ یا عیناً بیاورید یا حذف کنید." | `server/api/transcribe.py`, `server/schemas/workspace.py`, `server/nlp_tools/report.py`, `src/utils/api/transcriptionApi.ts`, `src/utils/hooks/useWorkspaceRecorder.jsx`, `src/pages/WorkspacePage.jsx`, tests for both sides | L |
| W1.6 | **Prompt-drift CI check.** New test: every prompt key in `DEFAULT_PROMPTS["prompts"]` is either referenced by code or explicitly listed as `UNUSED` in a registry constant with a Persian comment (refinement/chat/summary/letter/reasoning/job_extraction are currently unreachable in the 3-page app — registry makes this a conscious choice, not a drift). | new `server/tests/test_prompt_registry.py`, `server/database/config/defaults/prompts.py` (registry comment) | S |

**Acceptance (Wave 1):**
- A deliberately corrupted LLM response (test fixture) produces user-visible warnings in the API and UI, and the run is never blocked.
- A transcript with flagged low-confidence segments changes the system prompt (asserted in unit test) and the UI shows the badges.
- Gold-set score run before/after: abstention rule must not raise findings on gold notes (regression check).
- All CI green.

---

# Wave 2 — P1: audio pipeline + dictionary quality

**Order within wave:** W2.1 (ITN) and W2.2 (VAD) are independent; W2.3 (denoise) depends on W2.2 (sequencing denoise→VAD); W2.4–W2.5 (dictionary/biasing) independent; W2.6 (ASR eval harness) after W0.4 has real clips.

| ID | Task | Files | Effort |
|----|------|-------|--------|
| W2.1 | **Persian ITN module** `server/transcription/itn.py`: deterministic spoken→written normalization for numbers and units (پانصد → ۵۰، هفت دهم → ۷٫۱۰ pattern set, میلی‌گرم/میلی‌لیتر/روز/ساعت units; percent). Table-driven (Persian digit words + ordinals + fractions), value-preserving (property test: parse spoken and written forms back to the same canonical number). Applied in the **Shenava** output path (its model card documents spoken-form numbers) and behind `PHLOX_ITN=auto\|on\|off` (default `auto` = Shenava only) for other engines. Result metadata `itn_applied: bool`. | new `server/transcription/itn.py`; edit `server/transcription/audio.py` (`_run_shenava_inference`), `.env.example`; tests `server/tests/test_itn.py` (incl. "value never changes" property tests) | M |
| W2.2 | **Silero VAD.** Add optional extra `vad = ["silero-vad", ...]` (or vendor the ONNX via the existing model-download manager in `server/utils/whisper_models.py` — recommended, consistent with Shenava/Parakeet pattern). New `server/transcription/vad.py`: `trim_with_silero(wav) -> (wav, meta)` with the same fail-open contract as `trim_silence_wav`; keep ~200 ms pre/post margins. `prepare_audio()` becomes strategy-based: `PHLOX_VAD=auto\|silero\|energy\|off` (default `auto`: silero when available, else energy; `off` for A/B). Never let VAD drop the only speech: keep the existing "no voiced frames ⇒ return original" behavior. | new `server/transcription/vad.py`; edit `server/transcription/hygiene.py` (`prepare_audio`), `server/pyproject.toml`, `.env.example`, `server/tests/test_precision_phase1.py` (strategy matrix, incl. silero-missing fallback) | M |
| W2.3 | **Optional server-side denoise for files.** Extra `denoise = ["onnxruntime"]` + DeepFilterNet3 ONNX weights via the model manager (small, CPU). `server/transcription/denoise.py`: `denoise_wav(wav) -> (wav, meta)` with an SNR pre-estimate (frame-energy speech-vs-noise ratio on VAD labels); auto-apply only when estimated SNR < threshold (`PHLOX_DENOISE_MAX_SNR_DB`, default ~12) and setting enabled (`PHLOX_DENOISE=auto\|on\|off`, default `auto`). **Sequencing: denoise → VAD → ASR** (rework `transcribe_audio` order accordingly; keep original buffer available for `off`). Record `denoise_applied`, `snr_estimate` in `vad_meta`/result. If the extra is missing or model not downloaded: fail open to current path + debug log. | new `server/transcription/denoise.py`; edit `server/transcription/audio.py`, `server/pyproject.toml`, model manager, `.env.example`, tests (SNR gating, fail-open) | L |
| W2.4 | **Dictionary provenance + matching fixes.** (a) Add optional fields to entries: `src` (`inn`\|`fda`\|`curated`\|`generated`), `icd10` (optional str), `variants` (optional list of fa variants). Loader tolerates missing fields (backward-compatible with all existing JSON); `validate_terms.py` gains: `variants` must be non-empty strings, `src` enum check. (b) Backfill: mark `generated.json`/`expanded.json` entries `"src": "generated"`; everything else `"src": "curated"` (one-off script + commit). (c) **Fix `terms_for_context()` false positives:** word-boundary regex match (on ZWNJ-normalized, lowercased text) with min-length 2 and Persian whole-word boundaries, mirroring `search()`'s guards. (d) `terminology_reference_block()` sort: curated > generated, then length/frequency (currently only length/frequency). | edit `server/data/medical_dictionary.py`, `server/data/validate_terms.py`, `scripts/expand_dictionary.py`, term JSONs (one-off backfill script in `scripts/`), `server/tests/test_medical_dictionary.py` | M |
| W2.5 | **Biasing improvements.** (a) `build_initial_prompt()`: when the list is ≥10 terms, prefix with a short spoken-style Persian context line (CB-Whisper "spoken form hint" pattern) e.g. "پیاده‌سازی ویزیت پزشکی شامل مواردی مانند …" then the terms — total still ≤ 900 chars; keep pure list when short. (b) Include `variants` of high-priority terms in the bias list (deduped, counted against the same 60-cap). (c) Document the cap trade-off in the module docstring with the B-Whisper/OWSM citations. | edit `server/transcription/asr_context.py`, `server/data/medical_dictionary.py`, `server/tests/test_precision_phase1.py` | S |
| W2.6 | **ASR quality eval harness.** `scripts/eval_asr.py`: given the `data/eval/` gold audio set + engine config, run batch transcription, compute **WER + script-normalized WER** (canonical form: Persian digits, YK normalized, casefold) and optionally **BERTScore** (dev extra `eval = ["bert-score"]`, not a runtime dep), compare to committed baseline JSON, exit non-zero on regression. Also a `--compare A B` mode for model A/B (e.g., current large-v3-turbo vs `vhdm/whisper-large-fa-v1`). Manual-run (not CI) because of model weights. | new `scripts/eval_asr.py`, `server/pyproject.toml` (dev extra), `data/eval/README.md` (usage) | M |

**Acceptance (Wave 2):**
- ITN: property tests pass (canonical value preservation); Shenava path emits digit forms; `PHLOX_ITN=off` restores exact old output.
- VAD: on a synthetic low-SNR fixture, silero keeps speech and trims silence; silero missing ⇒ energy path unchanged (fail-open test).
- Denoise: on a MUSAN-mixed clip, WER improves vs no-denoise in `eval_asr.py` (documented in PR); on a clean clip, auto-mode does not apply (SNR gate) and WER unchanged.
- Dictionary: `terms_for_context` no longer matches 2-char terms inside longer words (regression test); provenance fields load; nightly term validator green.
- Gold-set score run still clean.

---

# Wave 3 — P1/P2: RTL hardening, verification pass, audit metadata, docs

| ID | Task | Files | Effort |
|----|------|-------|--------|
| W3.1 | **Normalization hardening** in `normalize_persian_text`: (a) NFC normalization; (b) strip leaked bidi control chars U+200E/200F/202A–202E/2066–2069 (keep ZWNJ U+200C — it is semantic); (c) document the digit policy in the docstring (Arabic-Indic→Persian; ASCII digits preserved — product decision, note it); (d) add `sanitised` count to return metadata or log for observability. | `server/transcription/language.py`, `server/tests/` (new cases: LRM/RLM/RI input, NFC-decomposed input, ZWNJ preservation, "HbA1c 7.2%" untouched) | S |
| W3.2 | **Mixed-script regression suite.** Server: pytest cases for drug+digit+unit+percent patterns (Persian and Latin digits) through `normalize_persian_text` + `terms_for_context` + `verify_note`. Frontend: vitest + rendering snapshot for a representative mixed note (drug list with "amoxicillin 500 mg"، "HbA1c 7.2%") asserting `dir="auto"` containers and LTR isolation of English terms. | `server/tests/test_mixed_script.py`, `src/test/` snapshot | S |
| W3.3 | **Optional LLM verification pass.** Setting `LLM_VERIFY_REPORTS=off\|on\|auto` (default `off`; `auto` = run when W1.1 found warnings or transcript had low-confidence flags). Second LLM call with a strict rubric prompt (Persian): "آیا هر عدد/دوز/نام دارو/نفی در یادداشت در متن اصلی آمده؟ فقط JSON {ok, issues:[...]} بده." Result attached to response metadata (`verification: {model, issues, duration}`); **never** auto-edits the note. Deterministic options (temp 0) for the verify call too. | `server/nlp_tools/report.py`, `server/nlp_tools/verification.py` (prompt + parse), `server/api/config/` (setting), tests (parse failure ⇒ treat as no-verify, never break the report) | M |
| W3.4 | **Audit metadata.** `/dictate` and `/api/workspace/report` responses carry a `pipeline` object: `{engine, model, vad: {applied, trimmed_ms, strategy}, denoise: {applied, snr}, itn: bool, flags_count}`. Log (structured) the same on report generation. No schema-breaking changes. | `server/api/transcribe.py`, `server/api/workspace.py`, `server/nlp_tools/report.py`, schemas | S |
| W3.5 | **Docs.** README (Persian) section: "لایهٔ بررسی اطمینان" — what the amber warnings mean, the settings (`PHLOX_VAD`, `PHLOX_DENOISE`, `PHLOX_ITN`, `LLM_VERIFY_REPORTS`), and the disclaimer that warnings are review aids, not validation. `.env.example` entries with defaults. Update the accuracy-plan references in code comments to this doc. | `README.md`, `.env.example`, comment cleanups | S |

**Acceptance (Wave 3):**
- Bidi-control-laden input round-trips clean; ZWNJ preserved; all existing normalize tests still pass.
- Mixed-script snapshots pass in both CI and dark mode.
- `LLM_VERIFY_REPORTS=auto` triggers on a fixture run and never breaks the report (parse-failure test).
- Audit metadata present in both endpoints (API smoke tests).

---

# Wave 4 — P2 strategic (separate, longer effort; data project, not code-only)

These are 6–12 month tracks; start with the data-collection protocol while Waves 0–3 ship.

| ID | Task | Notes | Effort |
|----|------|-------|--------|
| W4.1 | **Domain-adapted Persian medical ASR.** Consent + collect visit audio (start ≥50 h, grow to 150–300 h); gold-transcribe a held-out 10–20%; fine-tune **Shenava Koochik** (Apache-2.0 NeMo base, built for fine-tuning) — and/or `vhdm/whisper-large-fa-v1` lineage — with a **general+clinical mix** (do not fine-tune on clinical-only: evidence from the 2024 accented-clinical study). Export via the existing ONNX/tract pipeline; add as a new entry in the local model manager (same download pattern as Shenava/Parakeet). Evaluate with W2.6 harness before and after, on the mixed fa/en gold set (script-normalized WER + BERTScore). Ship only if it wins; keep biasing either way. | Separate repo/worktree for training; no PHI in training data without consent protocol; consider W4.3 masking | 4–8 weeks |
| W4.2 | **ICD-10 Persian mapping (one-time data project).** Obtain the Persian ICD-10 tabular list (PDFs public, e.g. ivsi.ir mirrors); build `{code, fa_name, en_name}` JSON for top ~2,000–3,000 conditions; LLM-assisted first pass + **clinician review**; merge `icd10` into `conditions.json` entries (field already added in W2.4). Version the mapping file; document source + access date. | Not an API; a curated data artifact in `server/data/terms/` | 2–4 weeks (review-dominated) |
| W4.3 | **PII masking for eval data.** Use OpenMed Persian PII ONNX classifiers (mBERT/TookaBERT INT4, public) via a dev-only script `scripts/mask_pii.py` for any corpus export/research sharing. Dev extra only. | Optional; needed before any external sharing of gold audio transcripts | S–M |
| W4.4 | **Two-pass pipeline decision.** Either (a) reinstate `prompts.refinement` as an explicit transcript-cleanup pass (ASR text → refined transcript → report) sharing the same guardrail constants from `verification.py`/prompt registry, or (b) delete the unused prompts. Requires product decision; W1.6 registry makes the current state visible. | Follows W1.6 | M (if (a)) |

---

## Sequencing & dependencies

```
W0 (measurement) ──┬──> W1 (live path: verify + uncertainty) ──> W3 (harden, verify-pass, audit, docs)
                   │
                   └──> W2 (ITN, VAD, denoise, dictionary, biasing, ASR eval)
W4.1/W4.2 data tracks: start W4.2 review + W4.1 consent/protocol during W0–W3; code lands after W2.6 exists.
```

- **PR suggestion (1 PR per row, each CI-green):**
  1. W0.1+W0.2+W0.3 (verification module, gold set, scorer) — no behavior change.
  2. W1.1+W1.2+W1.4 (verify in report path + abstention prompt) — additive API field.
  3. W1.3 (UI warnings).
  4. W1.5 (flags end-to-end).
  5. W1.6 (prompt registry test).
  6. W2.1 (ITN).  7. W2.2 (VAD).  8. W2.3 (denoise).  9. W2.4 (dictionary).  10. W2.5 (biasing).  11. W2.6 (ASR eval script).
  12. W3.1+W3.2 (RTL hardening).  13. W3.3 (verify pass).  14. W3.4+W3.5 (audit + docs).
- **Rollback safety:** every Wave-2/3 feature is behind a setting with the *current* behavior as an explicit option (`off`/`energy`/`auto` defaults chosen to be behavior-preserving where there is uncertainty: `PHLOX_VAD=auto` changes behavior silently by default — deliberate, since silero>energy is well-supported; `PHLOX_DENOISE=auto` defaults to *not applying* on clean audio; `PHLOX_ITN=auto` applies only to Shenava; `LLM_VERIFY_REPORTS=off` is a no-op by default).
- **What we deliberately do NOT change:** provider architecture, security model (CORS/SSRF/auth), the 3-page app shape, local engine routing (already correct), browser capture graph (keep WebRTC NS; W2.3 is server-side only for files).

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Negation/context checks false-positive and erode trust | Conservative design (W0.1c sentence-scoped), planted-error + gold-note both in CI baseline, warnings are review aids (never block copy) |
| Denoiser damages clean audio (Cleancoder caveat) | SNR-gated auto mode, `off` option, W2.6 A/B measurement on gold audio before defaulting |
| ITN mis-parses a spoken phrase into the wrong number | Table-driven, property tests (value preservation), default scoped to Shenava only, `off` restores raw |
| New optional deps bloat desktop builds | Extras only (existing `asr` pattern); online/Docker images unchanged; models via existing manager, lazy download |
| Gold audio contains PHI | `data/` gitignored, consent protocol in `data/eval/README.md`, W4.3 masking before any sharing |
| Prompt edits regress silently | W1.4/W1.6 prompt-regression + registry tests |
| LLM verify pass adds latency/cost | Off by default; `auto` triggers only on warnings/low confidence; temp-0, short rubric output |

## Success metrics (measured with W0.3 / W2.6)

1. **Planted-error catch rate** on `note_pairs_with_planted_errors.jsonl`: 100% (all planted number/negation/term errors flagged) — Wave 1.
2. **Gold-note false-positive rate**: 0 findings on 25–40 clean gold notes — every wave.
3. **ASR WER (script-normalized)** on the gold audio set: no regression on any wave; improvement after W2.2/W2.3 (documented per PR); W4.1 target: ≥ 20% relative WER reduction vs current best engine on the medical set.
4. **Prompt/model change discipline:** every prompt or model change ships with a score run in the PR description (checklist in CONTRIBUTING).
