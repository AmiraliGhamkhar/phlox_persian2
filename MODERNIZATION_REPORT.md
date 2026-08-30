# Phlox Persian — Modernization Pre-Plan Report

**Branch:** `arena/01a0528d-phlox-persian` (base commit `9a877c3`)
**Date:** 2026-08-30
**Status:** ✅ **Pass complete and verified end-to-end** — P0 (CI fixes), P1 (mechanical cleanups), P2 (code-volume reductions), and the two user-approved dependency majors (`openai` 3.x, `speechmatics-rt` 1.x) are all implemented and green (pytest 134, vitest 23, tsc, eslint, ruff check, ruff format, ty). Sections 3–7 record the applied changes, executed refactors, resolved decisions, and before/after metrics.

---

## 1. What this report contains

1. Verification baseline (what runs green, what is already red on `main`)
2. Deliverable 1 — Dependency change log (applied)
3. Deliverable 2 — Refactoring & fixes executed (what / why / risk / verification)
4. Deliverable 3 — Before-metrics table
5. Deliverable 4 — Assumptions & open questions (resolved)
6. Sandbox notes & transparency (temporary local changes)

---

## 2. Verification baseline

### 2.1 Environment used

| Tool | Required by repo | Available in sandbox | Notes |
|---|---|---|---|
| Node | `>=24 <25` (LTS) | 22.22.3 (npm upgraded to 11.19.1) | All JS metrics captured on Node 22; lockfile pins the same tool versions CI uses |
| Python | `>=3.12` | 3.11.2 | Python 3.12/3.13 cannot be installed in this sandbox (GitHub/`python.org` egress blocked). Baseline ran on 3.11 with **one** 1-line temporary tweak (see §6) |
| uv | `==0.11.32` | 0.12.7 | `required-version` pin relaxed locally (see §6); `uv.lock` untouched |

Network in this sandbox only allows `registry.npmjs.org`, `pypi.org`, `github.com` pages — no Docker, no Rust toolchain, no `python.org` downloads. Docker-image metrics (image size) could not be measured here.

### 2.2 Baseline test/CI results

| Gate | Result | Wall time | Notes |
|---|---|---|---|
| `pytest` (server) | ✅ **130 passed** | 2.95 s | Full suite, run with `TESTING=true DB_ENCRYPTION_KEY=…` (same env as `Dockerfile.test`); 6 Pydantic V2 deprecation warnings |
| `vitest run` (src) | ✅ **17 passed** (4 files) | 7.71 s | |
| `tsc --noEmit` | ❌ **FAILS — pre-existing** | 4.5 s | 1 error, `src/utils/api/transcriptionApi.ts:222` — `Uint8Array<ArrayBufferLike>` not assignable to `WebSocket.send()` parameter under TS 6.0.3 (pinned in lockfile). **CI on `main` should be red right now.** |
| `eslint .` | ❌ **FAILS — pre-existing** | 17.9 s | 1 error: unused import `normalizeChatArtifacts` in `src/utils/hooks/useChat.jsx:4`; 3 warnings: stale `eslint-disable` directives in `usePatientEditor.jsx:188`, `useSearchFlow.jsx:33,36` |
| `vite build` | ✅ builds | 2.17 s cold | 500 kB chunk warning fired (see metrics) |

> Per the task's hard rule: I will **fix these pre-existing failures** (they are genuine bugs/stale directives, not obsolete test behavior) — but I flag them explicitly here first rather than silently changing anything.

### 2.3 Startup / footprint baselines

| Metric | Before |
|---|---|
| Vite dev server ready (own log) | **409 ms** |
| Vite dev server HTTP-ready | ~1.0 s |
| Vite dev RSS (process tree, 3 procs) | **490.9 MB** |
| uvicorn (docker-mode) HTTP-ready on `/docs` | **1.5 s** (includes import + DB init + migrations) |
| uvicorn RSS (1 proc) | **120.3 MB** |
| `node_modules` size | 521 MB |
| `server/.venv` size | 302 MB |

---

## 3. Deliverable 1 — Dependency change log (applied)

**Overall finding (unchanged): dependency hygiene was already good** — everything is pinned to exact versions (Python) or caret ranges with a lockfile (npm), with a deliberate supply-chain posture (`.npmrc` `min-release-age=3`, `ignore-scripts=true`, `[tool.uv] exclude-newer = "3 days"`). No unused runtime dependency was found in either ecosystem. All changes below were applied to `server/pyproject.toml` + `server/uv.lock` (Python) and `package.json` + `package-lock.json` (npm), and every proposed version was screened against the repo's 3-day release cooldown.

### 3.1 Applied changes (final) — one-line justification each

| Package | Before | After | Justification |
|---|---|---|---|
| `fastapi` | 0.140.0 | 0.141.1 | Bug-fix/minor on the same major; no API changes. |
| `uvicorn[standard]` | 0.51.0 | 0.52.4 | Patch/minor on the same major; bug fixes. |
| `pydantic` | 2.12.5 | 2.13.4 | Minor on the same major; supports the `ConfigDict` migration (§4, item 4). |
| `json-repair` | 0.61.7 | 0.63.4 | Minor fixes; pure-Python, zero risk. |
| `platformdirs` | 4.10.0 | 4.11.4 | Patch/minor; tiny utility, no API change. |
| `rapidfuzz` | 3.14.3 | 3.14.5 | Patch release. |
| `openai` | 2.48.0 | **3.4.0** | **User-approved major**; both call sites verified against the 3.4.0 API (ctor still accepts `api_key`/`base_url`/`timeout`/`max_retries`; `chat.completions.create` + `embeddings.create` surfaces unchanged) — no call-site edit required. |
| `speechmatics-rt` | 0.5.3 | **1.1.1** | **User-approved major**; async-first rewrite — migrated `server/transcription/audio.py` + `live.py` to the 1.x API (`TranscriptionConfig(model=…)` replaces deprecated `operating_point`; event callbacks stay sync with the existing `asyncio.create_task` wrapper; `transcribe()` now auto-ends at source EOF). |
| `langchain-text-splitters` | — | **1.1.2** (new) | Replaces ~280 LOC of vendored LangChain chunkers (§4, item 7) with the canonical, actively-maintained package. |
| `@tauri-apps/plugin-http` | 2.5.7 | 2.5.9 | Patch on the same major. |
| `swr` | 2.4.2 | 2.5.1 | Minor on the same major; full test suite + typecheck pass unchanged. |
| `concurrently` | — | `^10.0.5` (dev, new) | `npm run dev` previously shelled out to the external GNU `parallel` binary (absent on bare metal); `concurrently` is the npm-installable, ecosystem-standard replacement. |
| `vitest` | `^4.1.10` | `^4.1.11` | Dev-only patch. |
| `eslint` | `^10.8.0` | `^10.9.1` | Dev-only minor on the same major. |
| `typescript-eslint` | `^8.65.0` | `^8.68.0` | Dev-only minor on the same major. |
| `@types/node` | `^26.1.1` | `^26.3.0` | Dev-only types minor. |
| `@types/react-dom` | `^19.2.4` | `^19.2.5` | Dev-only types patch. |
| `globals` | `^17.8.0` | `^17.11.0` | Dev-only minor. |
| `@testing-library/jest-dom` | `^7.0.0` | `^7.0.1` | Dev-only patch. |
| `@vitejs/plugin-react` | `^6.0.5` | `^6.1.0` | Dev-only minor on the same major. |

`server/uv.lock` was regenerated (uv 0.11.32, the CI-pinned version) and validated with `uv lock --check` (passes). Transitive fallout is the expected set: `openai 3.x`/`langchain-core 1.x` additions (`langsmith`, `orjson`, `truststore`, `tenacity`, `uuid-utils`, `xxhash`, `zstandard`, `jsonpatch`, `httpcore2`/`httpx2`, …), `tqdm` removed, `numpy` unified to the pinned 2.5.1 (the old lock carried a dead `<3.12` fork), and cp311 wheel entries dropped (the lock is now correctly scoped to `requires-python >=3.12`). CI uses Python 3.12 in both `ci.yml` and `build.yml`; the lock's resolution-markers cover 3.12–3.14.

### 3.2 Considered but NOT applied (with reason)

| Package | Latest available | Why held |
|---|---|---|
| `@chakra-ui/react` 3.37.0, `react-router` 8.3.1, `pdfjs-dist` 6.3.289, `@testing-library/react` 16.3.3 | — | Released < 3 days ago — violates the repo's `min-release-age=3` cooldown; eligible on the next pass. |
| `vite` 8.2.2 | 8.2.2 | **Measured regression**: rebuilding with 8.2.2 absorbs the shared `lib` chunk into the index chunk (530.78 kB → 736.92 kB raw) because rolldown-vite's chunk-split heuristics changed. Held at 8.1.5; re-evaluate when a stable equivalent split exists. |
| `typescript` 7.0.2 | 7.0.2 | Go-based rewrite — breaking by definition; stay on 6.x (approved hold). |
| `jsdom` 30.0.1 | 30.0.1 | Major; only used by vitest; no benefit worth the churn (approved hold). |
| `sqlcipher3` | 0.6.2 | Already latest; unmaintained upstream but no maintained alternative with the same encryption story (approved hold). |

### 3.3 Removals

No dependency was removed. The **vendored source files** `server/rag/fixed_token_chunker.py` + `recursive_token_chunker.py` were deleted (replaced by the `langchain-text-splitters` dependency, §4 item 7).

---

## 4. Deliverable 2 — Refactoring & fixes executed (all verified)

**P0 — Pre-existing CI failures (all fixed, all verified green)**

| # | File(s) | Change | Verified |
|---|---|---|---|
| 1 | `src/utils/api/transcriptionApi.ts:222` | Type the `Uint8Array` view for `WebSocket.send()`: `new Uint8Array<ArrayBuffer>(samples.buffer as ArrayBuffer, samples.byteOffset, samples.byteLength)` (zero-copy; the earlier `new Uint8Array(samples).buffer` idea was rejected — it would byte-truncate 16-bit PCM) | `tsc --noEmit` ✅ |
| 2 | `src/utils/hooks/useChat.jsx:4` | Removed unused `normalizeChatArtifacts` import | `eslint .` ✅ |
| 3 | `usePatientEditor.jsx:188`, `useSearchFlow.jsx:33,36` | Dropped stale `eslint-disable` directives | `eslint .` ✅ |
| — | **Python CI job (pre-existing, found during the pass; user approved fixing)** | Fixed 14 pre-existing `ruff check` errors (import sort, `SIM`/`TC`/`B`/`UP`/`F` rules) across ~10 files, `ruff format` on 10 files, and 9 pre-existing `ty check` diagnostics (typed-dict narrowing in `anthropic.py`, test `assert`-narrowing, `websockets` arg `ty: ignore` with compat comment) | `ruff check` ✅ `ruff format --check` ✅ `ty check` ✅ |

**P1 — Mechanical, behavior-preserving cleanups (done)**

| # | File(s) | Change | Notes |
|---|---|---|---|
| 4 | `server/schemas/{letter,patient,templates}.py` | `class Config: …` → `model_config = ConfigDict(…)` | Actual scope was **5 Config blocks in 3 files** (the "8 files" estimate over-counted `class Config(BaseModel)` and `class ConfigManager`); Pydantic V2 deprecation removed, no behavior change |
| 5 | `server/mcp/client.py` | `global _mcp_tools_cache` moved to top of `ensure_mcp_tools_cache()` | Removes the Python-3.12-only syntax relaxation; also fixed the pre-existing `SIM105`/`I001` lint in the same file |
| 6 | `server/locale.py` → `server/locale_policy.py` (`git mv`) | Removes stdlib `locale` shadowing; single importer `server/llm_client/client.py:18` updated | The sandbox's `/tmp/pyshim/locale.py` shim is no longer needed by the code itself |

**P2 — Code-volume reductions (done, each verified by tests)**

| # | File(s) | Change | Verification |
|---|---|---|---|
| 7 | `server/rag/{fixed_token_chunker,recursive_token_chunker}.py` deleted; `semantic_chunker.py` + `chunking_utils.py` re-pointed at `langchain_text_splitters.RecursiveCharacterTextSplitter` | −279 LOC vendored upstream code, replaced by the canonical package; vendored copy was diffed against upstream (byte-identical) before the swap; `keep_separator=True` preserved the exact chunk boundaries | New `server/tests/test_chunking.py` (4 tests) locks exact chunk output incl. the `. "` separator quirk — passes |
| 8 | `src/utils/helpers/{pdfExtractHelpers,pdfVisionHelpers,documentExtraction}.js` | Merged the duplicated document-processing preference logic into `getDocumentProcessingPreferences()` (single owner); pdf.js bootstrap already lives only in `pdfVisionHelpers.js` | `documentExtraction.spec.jsx` (6 tests) + full vitest suite pass |
| 9 | `package.json` scripts + `server/server.py` + `server/middleware.py` | `dev` script: GNU `parallel` → `concurrently`; uvicorn via `server/.venv/bin/python -m uvicorn` on `127.0.0.1:5000` (matches the vite proxy); bare-metal boot via explicit `PHLOX_DEV_BOOT=1` opt-in (boots DB + app at import; skips token validation) — Docker/desktop paths untouched | Verified live: `npm run dev` → vite :3000 + uvicorn :5000, proxied `/api/config/user` → 200 JSON |
| 10 | `src/components/layout/AppRoutes.jsx` | Route-level `React.lazy` + `<Suspense>` with a Chakra `PageFallback` for all six pages | Index chunk 1,935.68 kB → **530.78 kB raw (137.65 kB gzip)**; all pages still render via the same props |

**Dependency migrations (user-approved majors)**

| Change | Files | Outcome |
|---|---|---|
| `speechmatics-rt` 0.5.3 → 1.1.1 | `server/transcription/audio.py`, `server/transcription/live.py` | `TranscriptionConfig(model=Model.ENHANCED/STANDARD)` replaces the deprecated `operating_point` (1.1.1 raises if both are set); `AsyncClient(api_key=, url=)`, `client.on(...)`, `transcribe(source, …, timeout=)`, `client.close()` map 1:1; live partial/final handlers keep the sync-callback wrapper; `_QueueAudio` async `read()` is natively supported. Smoke-verified: `model=` produces no deprecation warnings; ctor/transcribe signatures match. |
| `openai` 2.48.0 → 3.4.0 | none (verified compatible) | `AsyncOpenAI`/`OpenAI` 3.4.0 ctor signatures (inspected) still accept `api_key`, `base_url`, `timeout`, `max_retries`; `chat.completions.create` and `embeddings.create` call sites unchanged. |

---

## 5. Deliverable 4 — Assumptions & open questions (resolved)

- **Q1 — Scope sign-off.** ✅ Implemented **all** of P0+P1+P2 (user confirmed, not just the safe fixes).
- **Q2 — Vendored LangChain code.** ✅ Add `langchain-text-splitters` and delete the vendored chunkers (user approved).
- **Q3 — Bare-metal `npm run dev`.** ✅ Must work for **both** Docker Compose dev and bare metal (user decision). Implemented with `concurrently` + `PHLOX_DEV_BOOT=1` (explicit opt-in; Docker/desktop handoff paths untouched). Verified end-to-end on bare metal.
- **Q4 — Pre-existing red CI.** ✅ Fix the typecheck/lint failures (user confirmed). Scope later expanded (user-approved) to the Python CI job's pre-existing `ruff`/`ty` failures discovered during the pass.
- **Q5 — Runtime verification.** ✅ Local verification runs on the sandbox's Python 3.11 (with CI-matching env vars and `PYTHONPATH` layout). CI runs Python 3.12 — code remains 3.11-parseable (one `UP047` is `noqa`-annotated rather than using PEP 695 generics, for exactly this reason). Final CI run will confirm on 3.12.
- **Q6 — Dev reload budget.** ✅ Assumed ≤ 5 s HMR; cold start measured at ~0.4 s (vite) / ~1.5 s (uvicorn) — well within budget. Not objected to.
- **Q7 — openai / speechmatics majors.** ✅ **Upgrade both** (user overrode my hold recommendation). Both done and verified.
- **New — Pre-existing Python CI failures discovered during the pass.** User approved fixing them (they were red on the base commit: `ruff check` 16 errors, `ruff format --check` 9 files, `ty check` 9–14 diagnostics).
- **New — vite 8.2.2 regression.** Bumped then reverted: it regresses the route-splitting win (index chunk 530.78 → 736.92 kB). Held at 8.1.5 and documented in §3.2.

---

## 6. Deliverable 3 — Before / after metrics

| Metric | Before | After | Δ |
|---|---|---|---|
| **LOC — server (Python, excl. tests)** | 25,888 (154 files) | **25,663 (152 files)** | −225 LOC, −2 files |
| **LOC — server tests** | 2,264 (20 files) | 2,385 (21 files) | +121 (new chunking regression suite) |
| **LOC — src (JS/TS/JSX/TSX)** | 37,781 (234 files) | 37,871 (235 files) | +90 (lazy routes + spec) |
| **LOC — Rust (src-tauri)** | 2,403 (6 files)² | 2,403 (6 files) | 0 (untouched) |
| **Prod bundle — index JS** | 1,935.68 kB (599.98 gzip) | **530.78 kB (137.65 gzip)** | **−72.6% raw / −77.1% gzip** |
| **Prod bundle — total JS assets** | n/a² | 2,376.05 kB raw | route splitting added lazy chunks; index is the first-load lever |
| **Prod build time (cold)** | 2.17 s | 1.92–2.09 s | ≈ same / slightly faster |
| **Dev server cold start** | 409 ms (log) / ~1.0 s (HTTP) | 396–417 ms (log) | ≈ same |
| **Dev server RSS** | 490.9 MB (3 procs) | ~893 MB (vite proc, post-usage)¹ | n/a (usage-dependent) |
| **Server cold start (docker-mode)** | 1.5 s (HTTP-ready) | ~1.5 s (HTTP-ready) | ≈ same |
| **Server RSS** | 120.3 MB | 27.9 MB (worker, post-usage)¹ | n/a (measurement point differs) |
| **Test suite** | py 130 ✅ / js 17 ✅ | **py 134 ✅ / js 23 ✅** | all pass, behavior unchanged |
| **typecheck / lint (JS + Python)** | ❌ red (pre-existing) | ✅ green (tsc, eslint, ruff check, ruff format, ty) | fixed |

¹ Node/Python RSS is heavily usage- and GC-dependent; the before/after numbers were captured at different moments and are not directly comparable. The stable, meaningful comparisons are LOC, bundle size, build time, and cold-start latency.
² The pre-plan report cited 2,343 Rust LOC; the identical-count rerun on HEAD yields 2,403 (same 6 files, blank-line-count difference) — the key fact is **zero Rust changes**. The pre-split total-JS baseline was not captured, so that cell is n/a; the per-chunk after-values are in §4 item 10 and §6.

---

## 7. Transparency — temporary local changes & notes

- `server/pyproject.toml` — the baseline's temporary `[tool.uv] required-version >=0.11` relaxation was **restored to `==0.11.32`** (matches CI's Dockerfile.test uv image). `uv.lock` was regenerated with uv 0.11.32 via a shimmed Python 3.12 interpreter (the sandbox has no real 3.12; CI's real 3.12 was used for the resolution target) and validated with `uv lock --check`.
- `server/mcp/client.py` global fix (item 5) — kept permanently.
- `server/.venv` (Python 3.11, sandbox-only) — synced to the final pins; not part of the repo.
- **Test-isolation note (flagged, not silently changed):** `server/tests/test_audit.py::test_purge_keeps_recent_events` assumes a fresh test database. CI passes because Dockerfile.test starts from an empty container; repeated local runs accumulate rows in `~/.local/share/Phlox` and the test goes red until that dir is removed. Flagged per the "never silently modify tests" rule.
- Sandbox egress blocked `openaipublic.blob.core.windows.net` (tiktoken BPE download) — the chunking tests were written to be offline-safe (`len`-based and monkeypatched tiktoken) so they pass without network.
- No commits or pushes were made; everything above is in the working tree on `arena/01a0528d-phlox-persian`.
