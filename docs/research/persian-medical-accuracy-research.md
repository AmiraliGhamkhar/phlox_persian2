# Reducing Hallucination and Improving Medical Accuracy in Phlox
## Research analysis + codebase assessment

**Date:** 2026-09-09 · **Scope:** ASR → denoising → LLM correction → RTL handling for Persian medical speech
**Audience:** engineers, product/clinical staff, medical & linguistic domain experts

---

## 0. Executive summary (for non-technical readers)

Phlox turns a recorded clinic visit into a structured Persian clinical note. Two places can introduce wrong information:

1. **The speech-to-text (ASR) step** can *invent* words — especially during silence or noisy audio. Research (Koenecke et al., *Careless Whisper*, FAccT 2024) found ~1% of Whisper transcriptions contain sentences that were never spoken, and 38% of those contained harmful content. In a clinic, an invented "no chest pain" or a fabricated drug name is dangerous.
2. **The LLM note-writing step** can *add or drop* clinical details while "cleaning up" the text. The industry term for this is *hallucination*.

**Where Phlox already stands** (verified in code): the system prompt explicitly forbids inventing facts, numbers, dosages or diagnoses and requires keeping negations; decoding is deterministic (temperature 0); a 5,891-entry Persian⇄English dictionary is injected as a grounded reference; silence trimming and per-segment confidence flags already exist; and the UI is properly RTL-aware. These match published best practices.

**The biggest gaps found:**
- Nothing *verifies* the LLM output against the transcript. Best practice is a deterministic post-check ("every number, unit, drug name and negation in the note must appear in the transcript") — currently missing.
- ASR confidence flags are computed but **never shown** in the UI or passed to the report generator, so low-confidence spans are silently trusted.
- No server-side denoising for uploaded/noisy files (only the browser's built-in mic noise suppression at capture time).
- No evaluation harness (golden transcripts) to measure whether changes actually reduce errors.
- Shenava (the Persian ASR model) outputs numbers in spoken form; a written-form normalization step (ITN) is missing.

**Where evidence is strongest:** English/general medical LLM hallucination control (system prompts, constrained decoding, verification), Whisper silence-hallucination mitigation (VAD-first), denoising-before-ASR, and Persian ASR models (Shenava, fine-tuned Whisper checkpoints).
**Where evidence is thin:** Persian-specific medical ASR fine-tunes (none public found), Persian ICD-10/SNOMED machine-readable mappings (none public found), and rigorous studies of LLM *Persian RTL output ordering* (mostly anecdotal bug reports).

---

## Evidence-confidence key

| Label | Meaning |
|---|---|
| **Strong** | Peer-reviewed or vendor-documented; multiple corroborating sources |
| **Moderate** | Single reputable source, preprint, or well-documented community practice |
| **Thin / unverified** | Anecdotal, vendor marketing, or absence-of-evidence — treat as hypothesis |

Glossary (for non-technical readers):
- **ASR / STT** — automatic speech recognition; converts audio to text.
- **WER** — word error rate; % of words wrong vs. a gold transcript. Lower = better.
- **VAD** — voice activity detection; finds where speech actually is.
- **Denoising** — removing background noise before ASR.
- **Biasing** — telling ASR "these words are likely in this recording" (names, drug names).
- **ITN (inverse text normalization)** — turning spoken numbers into written ones ("پانصد" → "۵۰").
- **Constrained decoding** — forcing the LLM output to match a strict format (e.g., JSON).
- **ZWNJ (نیم‌فاصله)** — the invisible half-space in Persian (e.g., می‌شود); removing it can change meaning.
- **Bidi** — the Unicode rules that lay out right-to-left text mixed with left-to-right text.

---

# Part A — Research findings

## 1. LLM hallucination control for Persian medical text correction

### 1.1 What the evidence says (best practices)

**Prompt-level controls (strong evidence, general + medical):**

- A September 2025 survey (Anh-Hoang et al., *Frontiers in AI*, DOI 10.3389/frai.2025.1622292) measured how much hallucination is *prompt-driven* vs *model-intrinsic*. Key findings:
  - **Vague prompts induce high hallucination rates across all models** — underspecification is a root cause.
  - **Chain-of-thought (structured step-by-step) prompting significantly reduced hallucination** in prompt-sensitive models (e.g., prompt-sensitivity score 0.15 → 0.06 on LLaMA-2).
  - **Negative prompting** — explicitly saying *"Do not include any information not present in the input text"* — measurably reduces fabrication in summarization tasks.
  - **Instruction-based prompting** (clear task structure) reduces ambiguity-driven errors but does not eliminate factual slips.
  - Few-shot examples help only when the examples are high quality.
  - A summary table of techniques (prompt calibration, negative prompting, RAG, post-hoc scoring, contrastive decoding, fine-tuning, RLHF) with feasibility ratings.
- A 2025 medical-hallucination review (medRxiv 2025.02.28.25323115, updated 2025-11) reports:
  - **CoT reduced hallucinations in 86.4% of tested comparisons** (FDR-corrected); e.g., Gemini-2.5-Pros went 87.6% → 97% accuracy when CoT was added.
  - **Ontology-enriched prompting** (extracting clinical concepts with BioBERT and constraining the prompt with ChEBI dosage/formulation facts) reduced entity errors ~33% vs. baseline prompts while keeping ~92% terminology consistency with FDA drug labeling.
  - **Self-reflection loops** ("check your draft against the source, flag anything unsupported") reduced *critical* hallucinations (misclassified disease types) by 41% in a pediatric-oncology use case.
  - Caveat: medical-specialized small models (MedGemma 28.6–61.9%) underperformed general frontier models — for a *faithful-transcription* task, a strong general model + strict guardrails beats a weak "medical" model.
- Practitioner guidance (Maxim, 2026-07) converges: structured output contracts, **explicit grounding rules repeated in the prompt**, an **"say you don't know / leave it out"** abstention instruction, and low temperature (0.1–0.3) for factual tasks.

**Output-level controls (strong evidence):**

- **Constrained decoding** (forcing valid JSON via a grammar) is now standard: JSONSchemaBench (arXiv 2501.10868, 2025-01) benchmarked Guidance/Outlines/XGrammar/llama.cpp/OpenAI/Gemini and found constrained decoding can even *speed up* generation ~50%. However, the field's central warning (repeated in 2026 production guides, e.g., tmls.nyc 2026-06): **"a guaranteed-valid response is not a guaranteed-correct one"** — schema enforcement kills malformed JSON and hallucinated field names (one study found 65% of schema errors in fine-tuned models were hallucinated keys + unclosed brackets) but *cannot* stop the model from putting a wrong dosage inside a valid field. **Constrain the wire format, never the thinking; then verify meaning separately.**

**Verification-level controls (moderate–strong evidence):**

- **Post-hoc checks** are the layer most often missing in production: entity reconciliation (numbers/names in output ⊆ input), groundedness scoring of each sentence against the source, and LLM-as-judge rubrics ("is every claim in the draft present in the transcript?"). The Frontiers 2025 table and the Maxim workflow both list post-hoc scoring/attribution as a core deployment practice.
- **Chain-of-Verification (CoVe)** style: a second LLM pass that adversarially checks the first pass's claims against the source. Evidence: moderate (multiple 2024–2026 studies; consistent direction, varies by model).

### 1.2 Persian / low-resource-specific considerations

- **Persian medical LLMs are research-grade and currently weak.** PersianMedQA (arXiv 2506.00250, 2025-08) — 20,785 expert-validated Persian medical multiple-choice questions from Iranian national exams, 40 models benchmarked:
  - Closed general models lead: **GPT-4.1: 83.09% (Persian) / 80.7% (English)**.
  - **Persian fine-tuned model "Dorna": only 34.9%** on the same Persian questions — "struggling with both instruction-following and domain reasoning."
  - Practical implication: for *faithful correction* (not diagnosis), run the strictest guardrails on a strong general model; do **not** assume a "Persian model" is safer.
- **Cultural/clinical cues live only in Persian.** PersianMedQA found 3–10% of questions are answerable correctly *only* in Persian (context lost in translation). So any pipeline step that internally converts to English risks losing meaning; keep processing Persian-first. (Strong — peer-reviewed benchmark.)
- **Persian pragmatics are under-served even by big models.** The taarof paper (arXiv 2509.01035, 2025-09) found all frontier models ≤42% on culturally expected Persian speech acts — a reminder that model *style* (formality, register) in Persian medical notes needs native review, not just fact-checking.
- **Morphology makes word-level diffing hard.** Persian agglutination and the ezafe chain mean "the patient's left knee pain" is a small number of tokens; a naive word-level compare between transcript and note will both miss real changes and flag harmless rewording. Normalized, character/ZWNJ-aware matching (what the codebase's `_normalise` starts to do) is required for any verification check. (Moderate — standard NLP practice; no Persian-specific public benchmark for "transcript faithfulness diffing" found — thin.)
- **No public Persian medical instruction-tuning corpus** (transcript→note pairs) was found. FarsInstruct (2024-07) is general-domain; MeDiaPQA is QA-format. So fine-tuning a correction model is not yet feasible with public data; prompt + verification is the evidence-backed path. (Thin for fine-tuning data; strong for "it's not there" as of 2026-09.)

### 1.3 Practical implications for implementation

1. Keep and *strengthen* the negative-prompting guardrails (they already exist and match the evidence).
2. Add the **abstention path explicitly**: "if a span is unclear, keep it verbatim and mark it" — the current prompt says "leave the section empty if not present" but doesn't cover *unclear-but-present* spans (the riskiest case: the model may 'fix' an unclear dosage into a plausible one).
3. Add a **deterministic post-hoc reconciliation** (numbers, units, drug names, negation markers) between transcript and generated note — cheap, auditable, and independent of model capability.
4. Optionally add a **verification LLM pass** (rubric-scoring) only when (a) ASR flags exist or (b) the note is long; measure cost vs. detected-error rate.
5. Keep temperature 0 + fixed seed for reproducibility (already done) and remember determinism ≠ correctness (the code docstring already says this correctly).

---

## 2. Persian medical dictionary & terminology resources

### 2.1 What exists (verified)

| Resource | What it is | Status |
|---|---|---|
| **Phlox bundled dictionary** (`server/data/terms/*.json`) | 5,891 fa⇄en pairs: conditions 1,684 · medications 1,195 · symptoms 832 · procedures 606 · labs 392 · anatomy 358 · obstetric 236 · oncology 225 · history 146 · plan 90 · vitals 78 · specialty 49. Quality-gated by `validate_terms.py`; ~1,400 entries combinatorially generated by `expand_dictionary.py`. | Internal, version-controlled. Broad coverage; precision risk on generated entries. |
| **MeDiaPQA** (Mendeley, 2023-05, CC BY 4.0) | 15,748 Persian doctor–patient dialogues, 7,704 QA pairs, 70+ specialties (University of Tabriz). | Public. QA-format; useful for evaluation/fine-tuning, not a term list. |
| **PersianMedQA** (arXiv 2506.00250, 2025-08; HF `MohammadJRanjbar/PersianMedQA`) | 20,785 expert-validated Persian medical MCQs, 23 specialties. | Public. Evaluation benchmark, not terminology. |
| **BioPars / BioParsQA** (PMC 2026-06) | First Persian biomedical LLM + 5,231 Persian medical QA pairs. | Public research model; QA format. |
| **ttcenter.ir medical glossary** (مرکز ترجمه‌های تخصصی, Ministry of Health translation center) | Public web glossary EN⇄FA medical terms (verified page, 2026). | Web-only as found; no machine-readable file or license confirmed — **thin/unverified** as a data source. |
| **WHO INN (International Nonproprietary Names)** | The authoritative source for standard drug names; published in multiple languages. The WHO publishes INN radical books / cumulative lists (PDFs verified at who.int). | Persian-language **machine-readable** list not verified — **thin**. Iranian FDA (سازمان غذا و دارو) publishes the marketed-drug list in Persian; API access not verified. |
| **ICD-10 in Persian** | Persian ICD-10 translations exist as PDFs/web content (e.g., ivsi.ir 2025-06, medicalrecords.blogfa.com). | **No public machine-readable {code ⇄ Persian name} mapping found — thin.** |
| **SNOMED CT in Persian** | — | **No public Persian mapping found — thin** (expect proprietary). |
| **Persian NER models** (HooshvareLab `roberta-fa-zwnj-base-ner`, Beheshti-NER 2020, BERT-PersNER 2021, PersoNER 2016) | General-domain Persian NER (person/loc/org/date). | Public, but **not medical** — limited use for clinical entities. |
| **OpenMed** (Maziyar Panahi, 2025-07) | Open-source biomedical NER (English; SOTA on 12 public datasets). `OpenMed Persian` collection (2026-05) = Persian **PII** token-classifiers (mBERT/TookaBERT ONNX). | Public. Useful for de-identification; not terminology. |
| **Lilak** (via awesome-persian-nlp) | Persian spell-checking dictionary. | Public. |
| **Awesome Persian NLP-IR** (github.com/mhbashari) | Curated index of Persian datasets/tools. | Public index — the best starting point for gap-filling. |

### 2.2 Assessment

- **Evidence is genuinely sparse for what Phlox would most want: an open, authoritative, machine-readable Persian medical terminology standard with crosswalks (ICD-10, SNOMED, INN).** The English ecosystem (UMLS, SNOMED, DrugBank, MedNLI, i2b2 corpora) has no Persian equivalent at similar quality. (Strong conclusion about the *gap*; each cell above individually verified where marked.)
- The realistic sourcing strategy is **hybrid**:
  1. Use the **WHO INN** + **Iranian FDA drug list** as the canonical source for drug names (grounding the 1,195 medication entries and their Persian spellings).
  2. Add **ICD-10 codes** to condition entries using the Persian ICD-10 tabular list (PDFs are public; a one-time manual/LLM-assisted mapping with clinician review is feasible — this is a data project, not an API).
  3. Keep the combinatorial generator but **mark generated entries** (e.g., `"generated": true`) so prompt injection can prefer curated entries, and have clinicians review high-frequency generated terms.
  4. Use **MeDiaPQA / PersianMedQA** for *evaluation* of the LLM layer, not as a dictionary.
- Dictionary grounding **reduces** hallucination mainly by (a) giving the LLM canonical spellings to pick from and (b) giving a deterministic verifier a ground-truth set of allowed drug/term strings. It does **not** validate medical content (a term can be canonical and still be the wrong term for the patient).

### 2.3 Practical implications

- Add source + code fields to dictionary entries (`"src": "INN-2024"`, `"icd10": "I10"`); even partial coverage is useful.
- Prefer curated > generated in prompt injection (the current `terms_for_context` does not distinguish them).
- Commission/validate a small set of **transliteration variants** for top-200 drugs (e.g., آموکسی‌سیلین / آموكسيسيلین / amoxicillin) so ASR biasing and matching survive spelling drift.

---

## 3. RTL handling for mixed Persian medical text

### 3.1 Text-processing / encoding side (strong evidence — this is mature standard practice)

**The core model.** The Unicode Bidirectional Algorithm (UAX #9) determines *visual* order from *logical* order. Text should always be stored and transmitted in **logical order** (the order a typist types); bidi marks and CSS handle display. For Persian-English clinical text the practical rules are (W3C/MDN guidance, corroborated by 2020–2026 engineering literature):

- Set **base direction** (`dir="rtl"`, `lang="fa-IR"`) on the document; use **`dir="auto"`** on dynamic text whose direction is unknown; use **`<bdi>` / `unicode-bidi: isolate`** for embedded fragments (drug names, IDs, code).
- Keep **code, URLs, emails, and LTR identifiers** in LTR containers; never let code blocks inherit RTL.
- **Numbers and units are weak/neutral characters**: they take the surrounding paragraph direction, so "۵۰ mg", "7.2% HbA1c" and "۶ ماه" can look different in different contexts even with identical code points. Rendering tests must cover digit + unit patterns explicitly.
- **NFC-normalize at every API boundary**; two "identical" Persian strings can differ in normalization form or in bidi control characters (LRM/RLM/RLI — U+200E/200F/202A-202E) that word processors and LLMs sometimes leak. Leaked bidi controls break string equality, search, and re-order display. (2026-04 localization engineering literature documents these failure modes.)
- **ZWNJ (U+200C) is semantically significant in Persian** (می‌نشیند vs. می نشیند; نمی‌تواند). Normalization must *preserve* ZWNJ inside words; only strip stray ZWNJs at token boundaries. Matching logic must strip ZWNJ *for comparison only* (the codebase already does this in `_normalise`).
- **Character-variant normalization for Persian**: ی/ي/ى/ئ → ی, ک/ك → ک, ة/ه/ۀ → ه, and Arabic-Indic ٠-٩ vs Persian digits ۰-۹ vs ASCII 0-9. ASR engines disagree on which they emit — the codebase's `normalize_persian_text` handles this correctly.
- **Persian code-switching reality** (Perle-ai benchmark, 2026-05, preprint): in genuine Persian–English code-switched speech, the median script-mix ratio is ~0.35 — short Latin terms embedded in longer Persian sentences, not 50/50. WER alone is an unreliable quality metric for this mix (transliteration variance: ۳۰.۸٪ WER on a semantically correct transcript); they recommend **BERTScore + script-normalized WER**.

### 3.2 LLM-side issues (thin evidence — flagged)

- **Do LLMs mis-order mixed Persian-English at generation time?** Evidence is **mostly anecdotal**: multiple 2025–2026 issue trackers report broken Persian rendering and "incorrect character ordering in mixed Persian-English text" (e.g., DeepSeek-LLM issue #82, 2025-12; LM Studio issue #568, 2026-05; CoPaw/QwenPaw issue #2120, 2026-03). Critically, **most of these are UI/rendering bugs, not model token-order bugs**: modern LLMs generally emit logical-order text, and the UAX#9 algorithm renders it correctly in a browser.
- What *is* reliably observed with smaller/less-Persian-tuned models: (a) wrong code points (Arabic ي/ك instead of Persian ی/ک), (b) dropped or extra ZWNJ, (c) occasional transliteration drift, (d) Latin drug names occasionally partially Persianized. These are **deterministic-fixable at the API boundary** (the codebase already fixes (a)).
- **No rigorous public benchmark of LLM Persian RTL output ordering was found** as of 2026-09. Confidence: thin. Recommendation: treat "model emits reversed/broken Latin inside Persian" as a *low-probability, high-impact* failure and guard against it with (1) a bidi-control sanitizer, (2) regression tests on mixed strings, and (3) a "Latin segments must not be reordered" spot-check in evaluation.

### 3.3 Practical implications

- The current CSS strategy (`dir="auto"` + `unicode-bidi: plaintext` for mixed content, `.ltr-content` isolate for English terms, LTR `code`/`pre`) matches W3C-recommended patterns.
- Add: NFC normalization + bidi-control-character stripping to `normalize_persian_text` (currently absent); a test suite for mixed-script clinical strings (drug name + digit + unit + %); and `dir="auto"` on dictionary hit rows (the English term is already isolated — good).
- For evaluation, adopt **script-normalized WER + BERTScore** for any mixed Persian-English ASR quality measurement (per the 2026-05 code-switching benchmark).

---

## 4. ASR pipeline for Persian medical audio

### 4.1 State of Persian ASR (strong, verified)

| Model / system | Persian performance | Notes |
|---|---|---|
| **Shenava Koochik v1.0** (Reza2kn, Apache-2.0; model card, 2026) | **WER 7.49%** (golden-6669) / **10.64%** (FLEURS-fa) | 114M FastConformer Hybrid RNNT/CTC, streaming, Persian-only, 16 kHz. **Outputs numbers in spoken form — ITN required.** Fine-tune base for domain adaptation. Phlox already ships its tract-streaming export. |
| **Whisper large-v3 / large-v3-turbo** (OpenAI, 2024) | Multilingual; Persian not a first-class language. Small Whisper models are poor on Persian (whisper-small ≈ 44.8 WER on Persian Common Voice; un-fine-tuned whisper-small 91.55 — Pour et al. 2024, secondary source — **moderate**). | Fine-tunes exist: `vhdm/whisper-large-fa-v1` (large-v3-turbo, **14.07% WER** on its clean Persian validation set, HF 2025); `AmirMohseni/whisper-small-persian` (25.8% WER FLEURS-fa). General multilingual WER across 99 languages ≈ 10.6% on FLEURS (commercial guide, 2026-03 — **moderate**). |
| **Speechmatics** (vendor, Persian added Dec 2023 as 49th language; "82.8% accuracy on Common Voice" — vendor claim, **moderate**) | Batch supports `auto` language + code-switching; **no Persian medical domain model** (medical domain is limited to 9 other languages, verified in `language.py` against vendor docs). Custom vocabulary: 300 terms (batch) / 100 words (realtime). | Phlox's handling of `expected_languages`/`default_language: fa` is correct per vendor semantics. |
| **AssemblyAI** (vendor docs, current) | Universal-2 supports Persian with **documented "moderate accuracy" (>25%–≤50% WER)** — the weakest documented tier. Universal-3.5 Pro (18 languages) auto-falls-back to Universal-2 for Persian. | Phlox's `speech_models` fallback list matches the documented recommendation exactly. |
| **Code-switching ASR** (Perle-ai benchmark, 2026-05, preprint) | ElevenLabs Scribe v2 led at 13.2% overall WER across 4 language pairs incl. Persian–English. | Confirms mixed fa/en is a distinct, harder task; WER understates quality here. |

### 4.2 Domain adaptation for *medical* speech (strong general evidence, thin Persian)

- **No public Persian medical-domain ASR fine-tune was found** as of 2026-09 (searched HF, arXiv, Iranian academic sources). Evidence is thin/proprietary — flag.
- Medical-domain fine-tuning **works in other languages** (pattern evidence, strong):
  - Korean telemedicine: fine-tuned Whisper large-v3-turbo on ~1,300 h of clinical telephone speech → significant WER/CER gains, **largest for patient (unstructured) speech** (2026-04, peer-reviewed).
  - Latin-American Spanish medical consultations: fine-tuned Whisper large-v3 on a small curated set → best open-source model; authors conclude "small investments in curating domain-specific data yield accuracy + reliability gains" (medRxiv 2026-07).
  - Accented clinical speech (2024-06, arXiv 2406.12387): fine-tuning improves *medical* entity WER by 25–34% relative; general-domain-only fine-tuning can *worsen* clinical performance — **keep general and clinical data mixed**.
  - IJCNLP 2025 Findings: a 300M **Persian** ASR pre-trained on relevant unlabeled data beat Whisper large-v3 (1.5B) on Persian — **data relevance > model size**.
- **Contextual biasing (the cheap, evidence-backed win):**
  - **B-Whisper** (Jogi et al., IEEE SLT 2024; arXiv 2502.11572, 2025-02): fine-tuning Whisper for prompt-based biasing gives **45.6% / 60.8% average improvement** on rare-word / unseen-word recognition, and the ability *transfers to languages not seen in fine-tuning* — which supports Phlox's approach of biasing a stock Whisper via `initial_prompt` for Persian. (The code's comment cites R-WER 23.7→18.0 / OOV-WER 60→37.1 from the paper's tables; the abstract-level figures are verified here — **moderate** for the exact deltas.)
  - **CB-Whisper** (LREC-COLING 2024): prompt-based biasing helps entity recall; long prompts degrade accuracy and can induce hallucination — keep lists short and high-precision (Phlox's 60-term/900-char cap is well within the 224-token window — good).
  - **OWSM-Biasing** (2025-06): prompt-based CB has O(n²) attention cost with large lists; dynamic-vocabulary biasing is better for thousands of words — relevant only if the dictionary grows much beyond a few hundred per session.
  - **Silence-hallucination mitigation (strong, multiple sources):** Whisper fabricates on silence/non-speech (up to 100% hallucination rate on non-speech audio; 2026 training-free methods, arXiv/analemma). Consensus stack: **VAD before ASR** (Silero or energy-based) → drop silent chunks → per-segment `no_speech_prob`/`avg_logprob` filtering → post-hoc artifact flagging (never silent deletion). `Careless Whisper` (2024) quantifies the harm. Phlox implements all of these at the right points.

### 4.3 Practical implications

- **Now:** Shenava Koochik as the Persian-first local engine (it is the best published small Persian model), Whisper large-v3-turbo for mixed fa/en, Speechmatics/AssemblyAI for online — the current routing is defensible; add `vhdm/whisper-large-fa-v1` as a candidate to A/B.
- **Data project (6–12 months):** collect consented visit audio (even 50–150 h), gold-transcribe a subset, and fine-tune (Shenava or large-v3-turbo) with a general+clinical mix; evaluate with script-normalized WER + BERTScore on a held-out Persian *mixed* set.
- **Biasing:** keep lists ≤ ~70 terms, per-encounter when context exists; add *spoken-form* variants of drug names for biasing (CB-Whisper shows spoken-form hints help); prefer vendor first-class vocabularies (Speechmatics) over prompts where available.
- **ITN:** add a Persian ITN step after Shenava (spoken "پانصد میلی‌گرم" → "۵۰۰ میلی‌گرم"), or at least in the LLM refinement contract ("convert spoken numbers to digits, preserve value exactly").

---

## 5. Audio denoising for clinical speech

### 5.1 Evidence (strong for "denoise before ASR helps"; moderate for magnitudes)

- **Denoising as an ASR frontend improves WER in noisy conditions without hurting clean audio:** the Cleancoder study (Springer, 2023-07) showed a learned denoising frontend reduces downstream WER across SNR 2.5–12.5 dB, *except* at very high SNR where reconstruction artifacts can slightly hurt a frozen ASR model — the fix is training/tuning on the enhanced audio, or keeping the denoiser light.
- **Model landscape (2025–2026 comparisons):**
  - **DeepFilterNet3** (MIT, actively maintained): PESQ 3.5–4.0+, STOI >0.95, ~40 ms latency, CPU-feasible, best on complex/non-stationary noise (chatter, monitor alarms), good echo/reverb handling.
  - **RNNoise** (Mozilla, 2017, BSD, 85 KB, <10 ms, no GPU; **no longer maintained**): fine for steady noise on constrained devices; weaker on complex noise.
  - Academic comparison (Mercubuana, 2025-06, VoiceBank+DEMAND): pre-trained DeepFilterNet3 clearly outperformed pre-trained RNNoise on STOI/PESQ/SegSNR.
  - Marketing claims like "WER −30% after denoising in STT pipelines" exist (service blogs, 2026) but are **not peer-reviewed — thin**; treat as upper bound.
- **Built-in browser processing:** `echoCancellation` + `noiseSuppression` in `getUserMedia` (WebRTC noise suppression) is exactly what Phlox's `audioRecorder.js` requests — a reasonable *light* denoiser, but its quality varies by browser/device, it is tuned for phone voice (can over-process clinical speech), and it only covers the live mic path, **not uploaded files**.
- **Clinical-audio specifics:** typical clinic noise = steady HVAC/fan (stationary, easy), monitor alarms and page (impulsive, hard), second conversation (speech-like noise, hardest for all denoisers). Diarization (speaker separation) is orthogonal and already exposed via Speechmatics config in Phlox.
- **Sequencing (consensus):** **capture (WebRTC NS on mic) → resample 16 kHz mono → (optional) offline denoise → VAD/silence trim → ASR (with biasing) → segment-level confidence filtering**. Denoising *before* VAD is fine because VAD thresholds are energy-based and denoised audio still passes them; denoising *after* VAD avoids processing silence. Either order is used in practice; the critical constraints are: never let the denoiser drop speech onsets (keep ~200 ms margins), and A/B measure WER per pipeline variant on your own audio.

### 5.2 Practical implications

- Live mic path: keep WebRTC NS (zero cost). Consider making `noiseSuppression`/`echoCancellation` user-selectable in Settings (some clinicians prefer raw audio).
- File path: add an **optional server-side DeepFilterNet3 pass** (ONNX CPU, ~2.3 M params, runs in seconds on a minute of audio) for uploads, gated behind a setting and *evaluated* (WER before/after on a small gold set) — the Cleancoder caveat says "no measurable benefit on clean audio", so the default should be "auto: apply when estimated SNR is low".
- Replace/supplement the energy VAD with **Silero VAD** (speech-specific, far better than RMS thresholds at low SNR; community standard per openai/whisper guidance) — low effort, well-tested.
- Record per-file pipeline metadata (denoise applied? VAD trimmed X ms? engine? confidence classes?) for audit and evaluation.

---

# Part B — Codebase assessment

> Verified against the repository at commit b585b4f (2026-09-09). File paths relative to repo root.

## B1. System prompt & hallucination controls

**What exists** (`server/nlp_tools/report.py`, `server/database/config/defaults/prompts.py`, `server/transcription/hygiene.py`):

- `REPORT_SYSTEM_PROMPT` contains the core guardrail set: *only state what is in the text; never invent drug/dose/lab/plan; keep numbers, units, drug names, abbreviations, identifiers exactly; preserve negations and uncertainty ("درد قفسه سینه ندارد" must not become "درد قفسه سینه"); leave missing sections empty; no definitive diagnosis or treatment recommendation outside the text; keep English medical terms untranslated; emit only valid JSON with fixed keys.*
- `deterministic_options()` forces temperature 0 + seed 0 for the note call, with an honest docstring that determinism ≠ no-hallucination.
- `PERSIAN_OUTPUT_INSTRUCTION` (locale policy) adds: no translation, preserve all clinical identifiers, Persian standard language only.
- JSON contract via `ClinicalReport.model_json_schema()` + `repair_json` fallback.

**Alignment with best practice:** **strong.** Negative prompting, instruction structure, output contract, deterministic decoding, and "don't diagnose" role framing are exactly the techniques the 2025 surveys rank highest for feasibility and effectiveness. The prompt also avoids the common failure of *conflicting instructions* (see below).

**Gaps:**
1. **No abstention rule for unclear-but-present spans.** The prompt says "if a part is missing, leave it empty" but not what to do when a span is *garbled* (e.g., an ASR-broken dosage). The highest-risk hallucination mode is the model "helpfully" repairing a garbled number into a plausible one. Add: "اگر بخشی از متن نامفهوم است، آن را بدون تغییر بیاور و با نشانه نامفهوم بودن علامت بزن؛ هرگز مقدار را حدس نزن."
2. **No post-hoc verification.** Nothing checks that every number/unit/drug in the output appears in the input (see Rec. P0-1).
3. **Two prompt universes that can drift.** The `prompts.py` "refinement" prompt (6 detailed rules incl. bullet-count preservation) is defined and shipped in DB defaults but **not used by any LLM path in this app** (the only LLM path is `generate_clinical_report`). It duplicates — in different wording — much of the report guardrails. Either wire it into a second refinement pass or delete it; as-is it's a maintenance hazard.
4. **ASR uncertainty not propagated.** The report call receives plain transcript text; the confidence classes and artifact flags computed by `build_hygiene_result()` are never passed to the prompt or UI (see B5).

## B2. Medical dictionary

**What exists** (`server/data/medical_dictionary.py`, `server/data/terms/*.json`, `scripts/expand_dictionary.py`, `server/data/validate_terms.py`):

- 5,891 fa⇄en entries, 12 categories (see §2.1). Loader is fail-open, ZWNJ-aware (`_normalise` strips U+200C for matching), cached.
- Three consumers: chat lookup (`search()`, rapidfuzz with careful short-term containment guards), **refinement/report grounding** (`terminology_reference_block()` — injects only terms *actually present in the draft*, with a precisely scoped exception: "normalize non-standard transliteration/English spelling to the table's standard form; change nothing else; touch nothing not in the table"), and **ASR biasing** (`asr_bias_terms()`, category-prioritized, 80-term cap).
- Quality gates in CI (`validate_terms.py` via `test_medical_dictionary.py`); deterministic generator with "no Latin in generated Persian, globally unique values" safety rules.

**Alignment:** **strong** — the scoped-exception design is a textbook-correct way to give the LLM *some* permission (spelling normalization) without opening the door to semantic editing. Grounding only with in-context terms (not the whole dictionary) is also the right call for prompt economy.

**Gaps:**
1. **No provenance.** Entries carry no source (INN/ICD/curated/generated). Generated combinatorial entries (e.g., severity-graded conditions) may not all be standard Persian clinical usage; a wrong "standard form" in the table *causes* the LLM to normalize toward it. Add `src`/`generated` fields; prefer curated in injection.
2. **Substring matching false positives in `terms_for_context()`.** Unlike `search()` (which guards short-term containment by length), the context matcher counts `fa_n in t_norm` — a 2–3 char term or a common word can match inside longer words (Persian has no spaces between ezafe links, making this more likely). Add word-boundary / min-length guards.
3. **No crosswalks** (ICD-10, INN, ATC) and no variant lists (transliteration drift of drug names). See §2.3.
4. **Coverage is breadth-first.** 1,195 medications is a good start vs. the Iranian marketed-drug list (thousands of brands + generics); brand names (very common in spoken visits) are largely absent from a generic-only list — a biasing and matching blind spot.

## B3. RTL handling

**What exists** (`index.html`, `src/index.css`, `src/transcription/language.py`):

- `<html lang="fa-IR" dir="rtl">`; Vazirmatn with separate Arabic + Latin subsets (good font engineering).
- `dir="auto"` + `unicode-bidi: plaintext` + `text-align: start` on all mixed clinical content; `.ltr-content` / `input[type=url]` / `code`/`pre` forced LTR with `unicode-bidi: isolate`.
- `normalize_persian_text()`: Arabic→Persian code points, Arabic-Indic→Persian digits, diacritic stripping, whitespace collapse, punctuation-attach (guarded for Latin identifiers/decimals).

**Alignment:** **strong** — matches W3C/MDN-recommended patterns for dynamic mixed-direction content.

**Gaps:**
1. **No bidi-control-character sanitization** (U+200E/200F/202A–202E) in the normalization path — LLM or word-processor-sourced transcripts can carry them, silently breaking equality/search/display.
2. **No NFC normalization step** (relevant if any text arrives pre-composed differently; cheap insurance).
3. **No mixed-script regression tests** for the clinically important patterns (drug + digit + unit + %, English abbreviations in Persian sentences) on either the server or UI side.
4. `normalize_persian_text` digit mapping converts Arabic-Indic (٠-٩) → Persian (۰-۹) but not ASCII 0-9 → Persian digits; whether that's desirable is a product decision (clinical notes often keep ASCII digits) — document the decision.
5. LLM output can occasionally contain reordered/fragile Latin spans (§3.2, thin evidence) — a low-cost spot-check in evaluation is the pragmatic guard.

## B4. ASR pipeline design

**What exists** (`server/transcription/audio.py`, `live.py`, `asr_context.py`, `language.py`):

- **Local:** whisper.cpp large-v3-turbo (fa/en/auto), **Shenava Koochik** (Persian-only, ONNX in-process, streaming cache-aware), Parakeet TDT (explicitly *not* Persian — and the app **rejects** fa/auto for Parakeet and en for Shenava with actionable errors — a correct and rare defensive choice).
- **Online:** Speechmatics Batch (language pinned `fa`/`en`, `expected_languages [fa,en]` + `default_language fa` for auto, medical domain **only** where the vendor offers it, custom vocabulary ≤300, fast-fail on terminal job states), Speechmatics Realtime (`additional_vocab` biasing, start-timeout widened when a vocab is present, max_delay/disfluency/diarization clamped to vendor-documented ranges), AssemblyAI (universal-3-5-pro → universal-2 fallback list, raw-key auth quirk handled, polling with deadline), Fireworks (auto→fa pinning with a correct rationale: provider default English would mangle Persian).
- **Biasing:** `build_bias_terms` = clinician name/specialty + dictionary layer, term sanitization (regex allowlist, length caps, dedupe), ≤60 terms / ≤900 chars prompt (inside Whisper's 224-token window), fail-open everywhere.
- **Hygiene:** `prepare_audio` (optional ffmpeg → 16 kHz mono WAV) → energy-VAD leading/trailing silence trim (200 ms margin, fail-open) → ASR → per-segment `ok/low_confidence/suspect` classification (avg_logprob ≤ −0.85 / no_speech_prob ≥ 0.65, env-tunable) → artifact flags (English *and* Persian caption/loop patterns; flags, never deletions).
- **Live fallback:** rolling 5 s window / 1.5 s hop for batch-only engines, capped buffer, with authoritative-false semantics so a dead live session falls back to full-file batch (documented in README and implemented in `useWorkspaceRecorder`).

**Alignment:** **strong — this is the most mature part of the system relative to the literature.** VAD-first, biasing-first, flag-don't-delete, vendor-faithful config, model-language incompatibility guards, and deterministic 16 kHz mono capture all match published recommendations.

**Gaps:**
1. **Shenava spoken-form numbers are not ITN'd** (model card: "Numbers are emitted in spoken form; apply Persian ITN when digits are wanted") — so "پانصد میلی‌گرم" can reach the note; the LLM prompt says preserve numbers exactly, so it will faithfully preserve the spoken form.
2. **Energy VAD vs Silero:** the RMS-percentile VAD is fine for clean office audio but degrades at low SNR; Silero is a drop-in upgrade (speech-specific, no GPU).
3. **No ASR quality evaluation loop** in the repo (no Persian medical gold set, no WER/BERTScore harness). `scripts/live_asr_smoke_test.py` tests connectivity, not quality.
4. **Live rolling-window fallback has no biasing** (only the Speechmatics realtime path sends `additional_vocab`) — acceptable (preview only; the authoritative transcript is the batch file) but worth documenting.
5. Whisper prompt biasing uses comma-joined terms without spoken-form hints (CB-Whisper: spoken-form hints improve entity recall) — minor, cheap.

## B5. Denoising & audio preprocessing

**What exists:**

- Capture: `getUserMedia({ echoCancellation: true, noiseSuppression: true })` (WebRTC NS), ScriptProcessor 16 kHz mono 16-bit WAV, linear resample — solid.
- File path: `prepare_audio` = optional transcode → silence trim. **No denoiser** on the server side.
- Sequencing: denoise (browser, mic only) → resample/mono → VAD trim → ASR — matches the recommended order (§5.1).

**Alignment:** **moderate.** The order is right and the mic path has light NS, but the file path (recorded visits on laptops, hospital dictation files, recordings sent to the app) has *zero* preprocessing beyond trim.

**Gaps:**
1. No server-side denoise option for noisy uploads (DeepFilterNet3 ONNX is a small, well-supported dependency — see §5.2).
2. No SNR estimation to *decide* whether denoising should run (Cleancoder's clean-audio caveat).
3. No per-file pipeline metadata (what was applied) — needed for audit and for the evaluation harness.

---

# Part C — Prioritized recommendations

### P0 — high impact, low effort (do first)

| # | Recommendation | Why (evidence) |
|---|---|---|
| P0-1 | **Deterministic output reconciliation:** before showing the note, extract from *transcript* and *generated note*: all numbers+units, all dictionary drug/term mentions, and negation markers (نمی‌/ندارد/نبود/منفی); diff them. Surface "note mentions X not found in transcript" as a review warning (never auto-edit). ZWNJ-aware, normalized matching. | Constrained output ≠ correct output (§1.1); the single cheapest guard against added/changed/dropped clinical facts. Works with any LLM provider. |
| P0-2 | **Wire ASR confidence into the flow:** pass the low-confidence/suspect segment spans into the report prompt ("these spans are uncertain — do not assert their content; keep them verbatim or mark them") and show a discreet badge on the transcript in the UI. | Flags are already computed (B4) but unused; flag-don't-delete is the established clinical-safety pattern; uncertainty propagation is standard RAG practice (§1.1). |
| P0-3 | **Add the abstention rule** for garbled-but-present spans to `REPORT_SYSTEM_PROMPT` (Persian text in §1.3 item 2). | The "repair a broken number into a plausible one" failure mode is the top clinical risk and is currently unaddressed. |

### P1 — high impact, moderate effort

| # | Recommendation | Why |
|---|---|---|
| P1-1 | **Persian ITN pass after Shenava** (spoken → digits/units), deterministic, with a "value must be preserved" contract; or at minimum instruct the LLM to digitize spoken numbers verbatim-true. | Shenava model card documents spoken-form output; notes need digits. |
| P1-2 | **Silero VAD** in place of (or alongside) the energy VAD; keep 200 ms margins; log `trimmed_ms`. | VAD-first is the strongest evidence-backed anti-hallucination ASR step; energy VAD degrades at low SNR. |
| P1-3 | **Evaluation harness:** 30–50 gold (visit audio → gold note) pairs; per-change regression of (a) note faithfulness (entity reconciliation pass rate, §P0-1 as the metric), (b) ASR WER/BERTScore with script normalization on a held-out mixed fa/en set. Use PersianMedQA/MeDiaPQA for LLM sanity, not note quality. | No public Persian medical eval exists; you must own yours. Without it, every prompt/model change is unmeasured. |
| P1-4 | **Dictionary hardening:** add `src`/`generated` provenance; word-boundary/min-length guards in `terms_for_context`; top-200 drug transliteration variants; brand-name coverage from the Iranian FDA list; ICD-10 codes for top conditions. | §2.3 — turns the dictionary from a glossary into a verifiable grounding layer. |
| P1-5 | **Optional server-side denoise for uploads** (DeepFilterNet3 ONNX, auto-apply on low estimated SNR, setting-gated, A/B measured). | §5.2 — file path currently has no denoising. |

### P2 — strategic (6–12 months)

| # | Recommendation | Why |
|---|---|---|
| P2-1 | **Domain-adapted Persian medical ASR:** consented visit audio (start small, grow), gold-transcribe, fine-tune Shenava Koochik (114 M, Apache-2.0, built to be a fine-tune base) or large-v3-turbo with a general+clinical data mix; evaluate with P1-3 harness; keep biasing in production meanwhile. | §4.2 — medical fine-tuning works in other languages (Korean 2026, Spanish 2026, accented 2024); no Persian medical fine-tune is public, so this is a genuine differentiator. |
| P2-2 | **Optional verification LLM pass** (rubric: every fact in the note present in the transcript? numbers? negations?) triggered when P0-1 flags or confidence is low; measure cost vs. catch rate. | Self-verification reduces critical hallucinations in medical settings (§1.1, 41% in one use case) — but only as a second opinion, never as the sole guard. |
| P2-3 | **Two-pass pipeline or prompt consolidation:** either reinstate `refinement` as an explicit transcript-cleanup pass (with the same guardrails shared from one module) or remove the unused prompt; add a CI check that every shipped prompt is referenced. | Drift between two guardrail wordings is a silent risk (§B1-3). |
| P2-4 | **RTL hardening tests:** bidi-control sanitize + NFC in `normalize_persian_text`; mixed-script regression suite (drug+digit+unit, abbreviations, IDs); `dir="auto"` audit on remaining dynamic strings. | §3 — mature standard practice; currently untested. |
| P2-5 | **PII de-identification option** using OpenMed Persian PII classifiers (ONNX, 2026-05) for research/eval data export. | Public, Persian-specific, relevant once an eval corpus exists. |

---

# Source list (accessed 2026-09-09)

**LLM hallucination control**
1. Anh-Hoang et al., *Survey and analysis of hallucinations in LLMs: attribution to prompting strategies or model behavior*, Frontiers in AI, 2025-09-30. https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1622292/full (peer-reviewed)
2. *Medical Hallucination in Foundation Models and Their Impact*, medRxiv 2025.02.28.25323115 (v2 2025-11-02). https://www.medrxiv.org/content/10.1101/2025.02.28.25323115v2 (preprint)
3. Maxim, *LLM Hallucination Detection and Mitigation: Best Techniques*, 2026-07-03. https://www.getmaxim.ai/articles/llm-hallucination-detection-and-mitigation-best-techniques/ (practitioner)
4. *Generating Structured Outputs from LMs: Benchmark and Studies* (JSONSchemaBench), arXiv 2501.10868, 2025-01. https://arxiv.org/abs/2501.10868
5. TMLS, *Structured Outputs and Constrained Decoding in Production*, 2026-06. https://www.tmls.nyc/research/structured-outputs-constrained-decoding
6. Tianpan, *Grammar-Constrained Generation*, 2026-04-16. https://tianpan.co/blog/2026-04-16-grammar-constrained-generation-output-reliability
7. Koenecke et al., *Careless Whisper: Speech-to-Text Hallucination Harms*, FAccT 2024 (arXiv 2402.08021, 2024-02). https://arxiv.org/abs/2402.08021

**Persian LLM/medical resources**
8. Kalahroodi et al., *PersianMedQA*, arXiv 2506.00250, 2025-08. https://arxiv.org/abs/2506.00250 (+ HF dataset)
9. Rostami et al., *PersianMind*, arXiv 2401.06466, 2024-01. https://arxiv.org/abs/2401.06466
10. *FarsInstruct*, arXiv 2407.11186, 2024-07. https://arxiv.org/abs/2407.11186
11. *Your LLM Must Learn the Persian Art of Taarof*, arXiv 2509.01035, 2025-09. https://arxiv.org/abs/2509.01035
12. *A pretrained biomedical LLM for Persian biomedical text mining* (BioPars/BioParsQA), PMC, 2026-06. https://pmc.ncbi.nlm.nih.gov/articles/PMC13518823/
13. Shahriar et al., *MeDiaPQA*, Mendeley Data, 2023-05. https://data.mendeley.com/datasets/k7tzmrhr6n/1
14. *A review on Persian question answering systems*, Springer, 2025-02. https://link.springer.com/article/10.1007/s10462-025-11122-z
15. awesome-persian-nlp-ir. https://github.com/mhbashari/awesome-persian-nlp-ir
16. ttcenter.ir medical glossary. http://www.ttcenter.ir/واژه‌نامه‌ها/واژه-نامه-پزشکی.html
17. WHO INN publications (radical book, cumulative lists). https://www.who.int/standards-and-publications/publications (PDFs verified)
18. Panahi, *OpenMed* blog, 2025-07-16; OpenMed Persian collection 2026-05. https://huggingface.co/blog/MaziyarPanahi/open-health-ai
19. Persian NER: Beheshti-NER arXiv 2003.08875 (2020); BERT-PersNER RANLP 2021; HooshvareLab roberta-fa-zwnj-base-ner.

**RTL / code-switching**
20. Perle-ai, *Benchmarking Commercial ASR Systems on Code-Switching Speech: Arabic, Persian, German*, 2026-05. https://www.researchgate.net/publication/405045841
21. W3C/MDN bidi guidance (dir, bdi, unicode-bidi: isolate/plaintext); Unicode Bidi Algorithm UAX#9. https://developer.mozilla.org/en-US/docs/Web/CSS/unicode-bidi
22. SimpleLocalize, *Unicode traps in localization*, 2026-04. https://simplelocalize.io/blog/posts/unicode-localization-guide/
23. Anecdotal RTL bug reports: DeepSeek-LLM #82 (2025-12), LM Studio #568 (2026-05), CoPaw/QwenPaw #2120 (2026-03).

**Persian ASR**
24. Reza2kn, *Shenava 1.0* collection + Koochik model card (published evals, spoken-form numbers, Apache-2.0), 2026. https://huggingface.co/collections/Reza2kn/shenava-10-open-streaming-persian-asr-and-captioning
25. Jogi et al., *B-Whisper: Improving Rare-Word Recognition of Whisper in Zero-Shot Settings*, IEEE SLT 2024 / arXiv 2502.11572, 2025-02. https://arxiv.org/abs/2502.11572
26. *CB-Whisper*, LREC-COLING 2024. https://aclanthology.org/2024.lrec-main.262/
27. *OWSM-Biasing*, arXiv 2506.09448, 2025-06. https://arxiv.org/abs/2506.09448
28. *Efficient ASR for Low-Resource Languages* (Persian 300M model), IJCNLP 2025 Findings. https://aclanthology.org/2025.findings-ijcnlp.99.pdf
29. Speechmatics, *Understanding Persian*, 2023-12; language list & medical-domain docs (current). https://www.speechmatics.com/company/articles-and-news/understanding-persian-bringing-a-new-language-to-speechmatics
30. AssemblyAI docs: Universal-3.5 Pro (18 langs, fa fallback), Supported Languages (Persian "moderate accuracy"), 2025–2026. https://www.assemblyai.com/docs/pre-recorded-audio/supported-languages
31. *Incorporating Error Level Noise Embedding for improving LLM-assisted Persian ASR robustness*, arXiv 2512.17247, 2025-12. https://arxiv.org/abs/2512.17247
32. Fine-tuned Persian Whisper checkpoints: vhdm/whisper-large-fa-v1 (14.07% WER, 2025); AmirMohseni/Whisper-Persian (25.8% FLEURS-fa); speechbrain commonvoice-fa. (HF model cards)

**Medical-domain ASR adaptation**
33. *Optimizing Whisper for Korean Telemedicine*, Digital Health, 2026-04. https://pubmed.ncbi.nlm.nih.gov/42011435/
34. *Benchmarking STT for Medical Consultations in Latin American Spanish*, medRxiv, 2026-07. https://www.medrxiv.org/content/10.64898/2026.07.14.26358062v1
35. *Performant ASR Models for Medical Entities in Accented Speech*, arXiv 2406.12387, 2024-06. https://arxiv.org/abs/2406.12387
36. *United-MedASR*, 2024-11. https://www.researchgate.net/publication/386374023

**Denoising**
37. *Bring the Noise: Noise Robustness to Pretrained ASR (Cleancoder)*, Springer, 2023-07. https://link.springer.com/chapter/10.1007/978-3-031-44195-0_31
38. *DeepFilterNet3 vs RNNoise* (VoiceBank+DEMAND), Mercubuana, 2025-06. https://publikasi.mercubuana.ac.id/index.php/sinergi/article/download/21917/9619
39. Noisereducer.ai, *DeepFilterNet vs RNNoise*, 2026-08. https://noisereducerai.com/blogs/deepfilternet-vs-rnnoise/ (vendor)
40. Whisper silence-hallucination mitigation threads: openai/whisper discussions #679/#1606/#1873; *Silence-Conditional Output Suppression*, 2026-03. https://analemma.ai/papers/714445d0/

**Codebase files assessed**
- `README.md`, `server/nlp_tools/report.py`, `server/data/medical_dictionary.py`, `server/database/config/defaults/prompts.py`, `server/transcription/{audio,hygiene,asr_context,language,live,parakeet}.py`, `server/locale_policy.py`, `src/index.css`, `src/pages/WorkspacePage.jsx`, `src/utils/audioRecorder.js`, `src/utils/hooks/useWorkspaceRecorder.jsx`, `server/tests/test_precision_phase1.py`, `scripts/{expand_dictionary,live_asr_smoke_test}.py`, `.env.example`
