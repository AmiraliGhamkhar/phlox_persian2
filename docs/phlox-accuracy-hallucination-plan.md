# Phlox Precision Plan — Accurate STT and Hallucination-Resistant Note Generation

Goal: make the two-stage pipeline (audio → transcript → structured clinical note) as
precise as current evidence allows, so that whatever remains is *caught by the system*
and *surfaced to the clinician*, never silently embedded in a note.

> **Honest framing first.** Published work shows these methods *reduce* hallucination;
> none eliminate it. A clinician-annotated framework over 12,999 generated sentences
> reports a best-practice hallucination rate of **1.47%** (NPJ Digital Medicine, CREOLA,
> 2025) — and the same study found physician-written notes also hallucinate
> (ambient notes 31% vs physician gold notes 20% of notes, PDQI-9 evaluation, Frontiers
> 2026). The design target is therefore: **rare → verified → flagged → reviewed.**

---

## 1. Why errors must be fixed at both stages

The LLM never hears the audio. It treats the transcript as ground truth, so ASR entity
errors (metformin → metronidazole) propagate into fluent, confident, wrong documentation.
A simulated evaluation of five ambient scribe platforms found ~**20% of transcript errors
carried into the note**, and overall **26.3% of key clinical elements were omitted or
captured erroneously** (MCP Digital Health, 2025). The SCRIBE evaluation framework
(npJ Digital Medicine, 2025) shows the same cascade in reverse: masking key transcript
terms degrades note accuracy, and systems fail specifically on **new/rare medication
names**. Conclusion: ~half the win comes from STT precision + confidence surfacing,
~half from generation discipline + verification.

---

## 2. Current state of this repo (audited)

| Stage | Today | Gap |
|---|---|---|
| Local ASR | whisper.cpp `temperature=0.0`, `verbose_json`, optional language hint; Shenava INT4 & Parakeet have bundled *vocabulary* files | No `initial_prompt` biasing; no VAD/silence trim on the batch path; segment confidences (`avg_logprob`, `no_speech_prob`) parsed then discarded |
| Remote ASR | Speechmatics batch/realtime, Fireworks, OpenAI-compatible | Speechmatics `custom_vocabulary` not wired from app context |
| Post-ASR | Language detection, Persian normalisation | No repetition-loop (deloop) or bag-of-hallucinations filtering; no low-confidence gating |
| Note generation | Per-field structured JSON (`schemas/grammars`), fuzzy condition normalisation (`rapidfuzz`), adaptive style refinement, human confirmation cards for writes | `refinement.py` passes a **random seed** ("diversity"); no evidence-first (quote) constraint; no claim-level verification; no numeric/negation guard; refinement can inject facts |
| Evaluation | unit tests + CI | No gold-standard ASR/note benchmark, no hallucination-rate telemetry |

---

## 3. Part A — Make the STT more precise (Persian / mixed fa-en)

### A1. VAD pre-pass + silence trimming  *(effort S, impact L)*
Whisper hallucinates strongly on silence and non-speech: silence at file start/end
"seemed to directly trigger hallucinations" (Koenecke et al., FAccT 2024; FAccT
reporting via Healthcare Brew). An effective Silero-VAD pre-pass gave the **largest
combined WER + hallucination reduction** of all tested mitigations, beating parameter
tuning alone (Barański et al., arXiv 2501.11378).
- Trim pre/post silence and long internal silences before posting to any whisper-like
  engine (the Shenava live path already sets `vad_filter=true`; do the same for the
  whisper.cpp batch path in `server/transcription/audio.py`).
- Keep dropped-span markers so timestamps stay aligned to audio.

### A2. Contextual biasing via `initial_prompt` / custom vocab  *(effort S, impact L)*
Zero-shot prompt biasing cut rare-word error rates dramatically: R-WER **23.7% → 18.0%**
and OOV-WER **60% → 37.1%** across 11 datasets (B-Whisper, arXiv 2502.11572); tree-based
biasing (TCPGen, arXiv 2410.18363) reduces domain WER without any fine-tuning, and
keyword-spotlight prompting improved unseen-domain WER by 5.1% (KG-Whisper).
- Build a per-encounter bias prompt server-side from data Phlox already has: patient
  name, UR number, clinician name, specialty, the patient's active problem list, recent
  medications, and clinic-wide high-frequency terms from
  `get_unique_primary_conditions()` (DB lookup already used in `summarisation.py`).
  Cap ≈ 180–200 tokens (Whisper prompt window).
- Pass as `initial_prompt` on whisper.cpp / OpenAI-compatible / Fireworks paths; map to
  `custom_vocabulary` on Speechmatics (its Enhanced API showed **0 hallucinations** in
  the clinical benchmark below).
- Reuse the Shenava/Parakeet vocabulary-file mechanism as the same "bias list" source
  so local models benefit identically.

### A3. Decoding parameters that fight hallucination  *(effort S, impact M)*
Barański et al. found **more hallucinations at higher beam sizes; lowest at beam=1**;
Whisper API params only give "limited" mitigation vs VAD + post-processing.
- Expose `beam_size=1` (greedy) as default with a settings escape hatch.
- Keep `temperature=0` (already set) for extraction tasks — but see B4: determinism
  helps *reproducibility*, it does not by itself fix hallucination (Communications
  Medicine, 2025 found temperature 0 gave **no significant improvement**).

### A4. Output hygiene: deloop + bag-of-hallucinations filter  *(effort S, impact M)*
Whisper loops ("the the the…") and emits training artifacts ("Subtitles by …", channel
outros) — in a dental clinical audio study Whisper produced **57 hallucinations
(28.5% of files)**, other engines 0 (JDR 2025, 10.1177/00220345251382452).
- Add a deterministic post-ASR stage in `server/transcription/text.py`: repetition
  collapse (deloop), BoH blocklist (maintained for fa+en clinical audio), and
  timestamp-gap detection; **flag** matched segments in the UI rather than silently
  deleting them.

### A5. Segment confidence + review gating  *(effort M, impact L)*
Harmful clinical hallucinations "blend into the clinical narrative and escape
detection" (JDR 2025). `verbose_json` already returns `avg_logprob` /
`no_speech_prob` per segment; today they are discarded.
- Persist per-segment confidence; mark low-confidence spans amber in
  `TranscriptionPanel`; click-to-hear on the span's timestamps.
- Any note content whose source quotes come only from low-confidence segments is
  auto-flagged for review in the save/confirmation flow (see D1).

### A6. Numbers, units and the fa/en boundary  *(effort M, impact L)*
Dose and digit confusion (۵ vs ۵۰, "500" vs "5,000", drug names mis-split at the
English insert) is the highest-severity STT failure class and WER does not see it —
entity-level metrics do (AssemblyAI reports clinical **Missed Entity Rate 3.2%** as the
quality metric with a dedicated medical mode; WER alone "can score well while
consistently missing drug names and dosages").
- Deterministic numeric entity extraction on the transcript (fa digits, Latin digits,
  Persian decimal `٫`, unit spellings); every number in the generated note must map to
  a transcript number or be flagged "needs verification — check against audio".
- Benchmark script (see C1) must report **MER-style entity recall**, not only WER.

### A7. Model choice and the Persian-specific ceiling  *(effort M, impact M)*
- Persian Whisper remains a low-resource problem: noise-robust correction with
  multi-hypothesis decoding moved WER **31.1% → 24.8%** on noisy Persian (arXiv
  2512.17247) — and note the same paper's warning: naively letting a general LLM
  "fix" the transcript made things *worse* (64.6%). Never let the note LLM rewrite
  raw transcript text (see B1/B6).
- Continued pre-training on unlabeled fa/en data has been shown to beat Whisper-large-v3
  for Persian (arXiv 2512.07277); synthetic doctor–patient dialogue generation over
  124k medical terms substantially cut medication-name WER without touching clinical
  audio (EACL 2026 industry track). Long-term: fine-tune or train a Phlox "clinical-fa"
  ASR variant; short-term just quantify the gap with C1.
- Offer GPT-4o-Transcribe-class and Speechmatics-enhanced endpoints in the remote
  picker with biasing wired (A2): in the JDR 2025 clinical benchmark those were the
  two cleanest rows (0% hallucinations; GPT4o-transcribe-corrected had the best
  ROUGE/BERTScore).

---

## 4. Part B — Make note generation faithful to the transcript

### B1. Evidence-first, two-phase field filling  *(effort M, impact L)*
Replace "generate field text from transcript" with:
1. **Extraction**: per template field, model outputs `quotes[]` (verbatim transcript
   spans + segment ids) plus `not_documented` as a legal answer;
2. **Composition**: rewrite quotes into note prose.
Server-side validator rejects any quote that isn't a normalised substring of the
transcript (ZWNJ/digits normalised) → one retry → otherwise flag. This is exactly the
"citation/constraint" mechanism that produced the largest safety gains in the structured
patient-artifact study (citation requirements + constraint checking contributed most to
safety improvements; unsupported claims 43.6% → 21.1% in the agent workflow, and naive
raw-RAG *increased* hallucinations 8.7×, medRxiv 2026.02.13.26346256). Enforced
citations suppress unsupported content in medical RAG per model family (MDPI Appl. Sci.
2026).

### B2. Chain-of-Verification pass before save  *(effort M, impact L)*
CoVe (Meta, ACL Findings 2024): draft → plan verification questions → answer them
*without attending to the draft* → revise. FACTSCORE 55.9 → 71.4 on long-form
generation; factored answering is essential or the model copies its own hallucinations.
Applied here: extract atomic claims from the composed note → per-claim entailment check
against the transcript (independent call, draft hidden) → drop or flag unsupported
claims. VeriFact-CoT reports the same pattern cutting hallucination 25% → 12% overall,
19% → 9% on GPT-4 (arXiv 2509.05741). Persist a per-save **verification report** (JSON)
into the existing audit log (`server/api/audit.py`) for retrospective QA.

### B3. Prompts: encode what actually worked  *(effort S, impact L)*
The Communications Medicine multi-model study (300 planted-false-detail vignettes) is
sobering: LLMs elaborated on fabricated details **50–82%** of the time; a *mitigating
prompt* (use only provided information, acknowledge uncertainty, do not speculate) cut
the mean from **66% → 44%** and GPT-4o from **53% → 23%** — big for a zero-code change,
though far from elimination (that's what B1/B2/D are for). Encode in
`scribe_system_prompt` and the refinement prompt:
- "Only document content present in the transcript. If a section has no evidence,
  output not_documented."
- "Do not expand abbreviations" (speculative abbreviation expansion + attribution swaps
  + emotional exaggeration were the top LLM error classes when transforming psychiatric
  documentation — JMIR 2026).
- "Preserve negations verbatim" + a deterministic NegEx-style check: for every
  "no/without/بدون/منفی" token pair between transcript and note, compare polarity;
  flips → block save pending review.
- "Never copy numbers from examples or priors" (style-example contamination — see B7).

### B4. Determinism: kill the random seed  *(effort S, impact M)*
`refine_field_content` currently uses `random.randint` "for diversity" and forwards it
with structured output. For clinical extraction, reproducibility is a feature: fixed
seed (or none), temperature 0, and record model+seed+prompt-hash alongside the note so
every save is re-runnable in evaluation. (Determinism ≠ anti-hallucination — see A3 —
but it is required for the regression suite in C1 and for legal-grade auditing.)

### B5. Strict structured outputs  *(effort S, impact M)*
Tighten `server/schemas/grammars`: `additionalProperties: false`, enums for closed
sets, numbers typed as `{value: number, unit: string, verbatim: string}` so "۵ میلی‌گرم"
survives as-is; `verbatim` is then checked against the transcript (B1 validator reuses
this). When the local llama.cpp sidecar is in use, compile the schema to a GBNF grammar
so decoding cannot structurally drift; `repair_json` remains only as a compat shim,
never as a licence to invent.

### B6. Refinement containment (style must not add substance)  *(effort M, impact M)*
The CREOLA study's own warning: their new **template-driven refinement increased major
hallucinations** vs the simpler pipeline. After the adaptive style pass, run the entity
diff (names, numbers, negations, drugs) pre- vs post-refinement; any new entity in the
polished text → revert to draft and log.

### B7. Example-leakage guard for adaptive refinement  *(effort S, impact M)*
Few-shot style examples (the "adaptive" feature) can bleed content across patients.
Deterministic n-gram overlap check between the produced field and the *example texts*
(ignoring boilerplate/field labels); overlap of clinical tokens → flag. Keep examples
style-only in the prompt ("mimic tone and ordering only; content must come from the
transcript").

### B8. Prompt-injection fence between transcript and instructions  *(effort S, impact M)*
The chat engine already has an UNTRUSTED CONTENT RULE; apply the same fence to note
generation: transcript is wrapped in data markers, and system prompts state that
imperatives inside it are patient speech, not instructions to the model. (Adversarial
elaboration rates above show how cheaply injected "facts" ride along.)

### B9. Consistency voting on high-risk fields  *(effort S, impact M)*
For medications/doses/problem lists only: sample k=3 extractions at low temperature,
keep agreed entities, and surface disagreements as review chips. Self-consistency is
cheap, local-model-friendly, and concentrates review effort where harm lives.

---

## 5. Part C — Prove it: "Phlox Bench" evaluation harness

Everything above is a bet unless measured. Build first or alongside Phase 1:

**C1. Gold set + metrics**  *(effort M, impact L)*
- 30–60 simulated encounters (fa and fa/en-mixed, clean + noisy, with crosstalk),
  professional transcripts, clinician gold notes, plus *adversarial variants* with one
  planted false detail per note (to check non-elaboration, per B3 methodology).
- ASR metrics: WER/CER, **entity recall (MER)** for drugs/doses/dates/numbers,
  hallucination rate on silence/noise segments, confidence calibration.
- Note metrics: claim-supported rate (B2 validator output), fabricated-claim rate,
  omission rate, negation/assertion flips, numeric exactness — i.e. the CREOLA error
  taxonomy so the numbers are comparable to published literature (1.47% hallucination /
  3.45% omission is the published bar to chase).
- Optional LLM-as-judge for fluency/structure only — never for factuality (factuality
  stays deterministic: quotes, diffs, negation checks).

**C2. Nightly regression gate**  *(effort S, impact M)*
The repo already has a `nightly.yml` workflow: run the bench on every default-model /
prompt change; fail the build on fabricated-claim-rate or numeric-error regressions;
publish a per-version scorecard into the changelog modal. Model/prompt updates then
become *measured* rather than vibes (SCRIBE's stated governance use-case).

**C3. Real-world shadow audit**  *(effort S, impact M)*
Per-save verification reports (B2) aggregated monthly: flag-clearance rate, %
clinician-edited flagged items, per-provider hallucination telemetry. This gives Phlox
its own quality signal for free, mirroring what ADS governance papers recommend.

---

## 6. Part D — The human loop stays by design

- **D1. Confirmation card upgrade:** the existing write-gating cards gain a per-note
  summary: `12 claims verified · 2 need review`, each review chip deep-links to the
  transcript segment + audio timestamp. Saves with unresolved flags require an explicit
  "accept anyway" (audited). Every reputable ambient scribe routes through clinician
  review before finalisation — keep Phlox's human-in-the-loop as the last defence, not
  the only one.
- **D2. Provenance inline:** small evidence markers next to generated sentences
  (hover → transcript quote); builds trust and makes review fast, which the patient-
  documentation studies show is where residual errors get caught.
- **D3. Diff view** between raw draft and polished note so the style pass is inspectable
  (directly addresses refinement containment, B6).

---

## 7. Rollout

| Phase | Contents | Effort | Expected effect |
|---|---|---|---|
| 1. Quick wins (no model changes) | A2 prompt biasing, A3 greedy default, A4 BoH/deloop, B3 prompts, B4 determinism, B8 fence | S–M | Kills most silence/artifact hallucinations; adversarial-study-style prompt cuts ~30–40% relative |
| 2. Verification core | B1 quote-first + validator, A1 VAD, A5 confidences, A6 numeric guard, B5 strict schemas | M | Unsupported claims become mechanically detectable and mostly impossible to save silently |
| 3. Assay & containment | B2 CoVe pass + audit reports, B6 refinement diff, B7 leakage guard, B9 voting | M | Catches what phase 2 misses; refinement can no longer add facts |
| 4. Bench & governance | C1–C3, D1–D3 | M | Measured regression-proof improvement; clinician workflow around residual risk |
| 5. Model programme | A7: benchmark matrix, "clinical-fa" fine-tune / synthetic-data ASR, provider upgrades | L | Raises the ceiling where Whisper-family struggles (Persian medical vocabulary, code-switching) |

---

## 8. Key evidence (short list)

1. Koenecke et al., *Careless Whisper: Speech-to-Text Hallucination Harms*, FAccT 2024 — Whisper hallucinates on silence/non-speech; harmful in 38% of cases; trimming silences reduces it.
2. *Transcription Accuracy of ASR for Orthodontic Clinical Records*, JDR 2025 (doi 10.1177/00220345251382452) — Whisper 28.5% of files hallucinated in clinical audio; Speechmatics Enhanced & GPT-4o-Transcribe 0%; noise raises WER; clinically significant errors 2–66%.
3. Barański et al., *Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio*, arXiv 2501.11378 — beam=1 best; Silero-VAD + deloop + bag-of-hallucinations post-processing strongest practical mitigations.
4. Jogi et al., *Improving Rare-Word Recognition of Whisper in Zero-Shot Settings*, arXiv 2502.11572 — prompt biasing R-WER 23.7→18.0%, OOV-WER 60→37.1%; fine-tuned B-Whisper generalises.
5. Lall & Liu, *Contextual Biasing … without Explicit Fine-Tuning (TCPGen)*, arXiv 2410.18363 — biasing beats overfit fine-tuning on domain terms.
6. Asgari et al., *A framework to assess clinical safety and hallucination rates of LLMs for medical text summarisation (CREOLA)*, npJ Digital Medicine 2025 (PMID 40360677) — 1.47% hallucination / 3.45% omission at best; template refinement trade-offs; iterative workflow measurement is what got errors below human baseline.
7. *Multi-model assurance analysis … adversarial hallucination attacks*, Communications Medicine 2025 (doi 10.1038/s43856-025-01021-3) — 50–82% elaboration of planted false details; mitigating prompt 66%→44%; temperature 0 no effect.
8. Dhuliawala et al., *Chain-of-Verification …*, ACL Findings 2024 — FACTSCORE 55.9→71.4; verification must not attend to the draft.
9. *VeriFact-CoT*, arXiv 2509.05741 — hallucination 25%→12% (GPT-4: 19%→9%) with verify-reflect-cite.
10. *Representation Before Retrieval: Structured Patient Artifacts …*, medRxiv 2026.02.13.26346256 — raw RAG raised unsupported claims 8.7×; citation enforcement + constraint checks drove safety.
11. *Reducing Hallucinations … Citation-Enforced Prompting in Medical RAG*, MDPI Appl. Sci. 2026 — strict-citation prompts suppress unsupported content; verbosity ratio as uncertainty proxy.
12. *Evaluating Quality and Safety of Ambient Digital Scribe Platforms*, MCP Digital Health 2025 — 26.3% key elements wrong/missing; ~20% transcript errors propagate; platform variability demands objective benches.
13. *SCRIBE: evaluation framework for ambient digital scribing tools*, npJ Digital Medicine 2025 (doi 10.1038/s41746-025-01622-1) — structured evaluation incl. error-injection simulation; new-medication capture is the weak point.
14. *Errors in AI-transformed patient-centered mental-health documentation*, JMIR 2026 (PMID 42054574) — top LLM error classes: misinterpretation, attribution swaps, speculative additions, abbreviation expansion.
15. *Incorporating Error Level Noise Embedding for Persian ASR correction*, arXiv 2512.17247 — Persian multi-hypothesis correction 31.1%→24.8% WER; naive LLM transcript rewriting made errors worse (64.6%).
16. *Efficient ASR for Low-Resource Languages (fa/ar/ur)*, arXiv 2512.07277 — continual pre-training beats Whisper-large-v3 on Persian.
17. *Synthetic Doctor-Patient Dialogue Generation for Robust Clinical ASR*, EACL 2026 industry — 1B synthetic audios over 124k medical terms; large medication-WER reduction without real clinical audio.
18. *Assessing the quality of AI-generated clinical notes (Ambient/PDQI-9)*, Frontiers in AI 2026 — hallucinations in 31% ambient vs 20% physician gold notes; validated scoring tool.
19. AssemblyAI *Medical Mode* benchmark materials — Missed Entity Rate (not WER) as the clinical ASR metric; 3.2% MER vs ~20% without a medical mode.
20. *Accuracy and Safety of an AI Ambient Scribe vs Handwritten Notes* (Research Square, Groote Schuur 2026) — real-world scribe beat handwritten notes on quality and severe errors; residual AI errors traced to upstream transcription → reinforces A1–A6.
