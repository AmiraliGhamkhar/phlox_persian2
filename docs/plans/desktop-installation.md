# Desktop Installation Plan — Fast, Full, Secure

Goal: one-click desktop installs that are **fast** to download/install/first-run,
**full** (everything needed works out of the box and stays current), and
**secure** (signed, verified, hardened, reproducible).

Grounded in the current pipeline state as of v2.2.4.

---

## 1. Where we are today

| Area | Current state | Gap |
|---|---|---|
| Release builds | `.github/workflows/build.yml` — **Docker image only** (→ `ghcr.io`). macOS DMG and Linux Flatpak jobs removed; Windows desktop installer is built locally (`npm run tauri-build`) | No CI desktop build job, no published desktop installer |
| Python backend | Nuitka `--mode=standalone` (`src-tauri/build-server.sh`), ccache + Nuitka cache in CI | Size not measured/optimized; no stripping audit |
| Sidecars | llama.cpp / whisper.cpp / parakeet.cpp compiled from **pinned commits**, bundled per target-triple as `externalBin` | Good — keep |
| Models | Downloaded at first run from Hugging Face (`server/utils/{llama_models,whisper_models}.py`), progress via SSE, cleanup on cancel/disconnect (F-11) | No resume after interruption; no offline option |
| Updates | **None** — no `plugins::updater` config, no signing keys | Users re-download full installers manually |
| Windows signing | `certificateThumbprint: null` — unsigned | SmartScreen warnings; easy to tamper/imersonate |
| Supply chain | Actions pinned by SHA, `persist-credentials: false`, locked deps (uv.lock, package-lock, Cargo.lock), Dependabot | Dependency-audit CI job is informational, not gating |
| User data | Lives in OS data dir (`<data_dir>/Phlox/phlox_database.sqlite`, SQLCipher) — separate from install dir | Good — reinstalls/updates never touch PHI |
| Runtime hardening | Local request token, host validation, rate limiter, body limits, audit log | `PHLOX_DEV_BOOT` env bypass should be impossible in packaged builds |

---

## 2. Phase 0 — Measure the baseline (before any change)

You cannot improve what you don't measure. Effort: **S (½ day)**.

1. Record current artifact sizes: DMG, installed app dir, `server_dist` (Nuitka standalone), llama/whisper binaries.
2. Record cold-start timings (scriptable): app window visible → server `/health` OK → ASR ready → first transcription done.
3. Record first-run network usage: bytes downloaded for models on a clean profile.
4. Put these numbers in this doc as the baseline row; every later phase must show its delta.

Acceptance: a table of numbers committed to this file; a repeatable measurement script in `scripts/`.

---

## 3. Phase 1 — Close the security gaps (cheap, high value)

### 1.1 Windows code signing (M)
- Obtain an Authenticode **OV certificate** (or Azure Trusted Signing — cheaper, no HSM logistics).
- CI: sign the NSIS installer **and every bundled executable** (`phlox-server`, sidecars, main exe) with `signtool sign /tr http://timestamp.sectigo.com /td sha256 /fd sha256`.
- Tauri config: set `bundle.windows.certificateThumbprint` **or** sign post-build in CI (recommended: post-build step so the same artifact flow works for Trusted Signing).
- Acceptance: `Get-AuthenticodeSignature` valid on installer; no SmartScreen "unknown publisher" after reputation builds.

### 1.2 Auto-updater with signature verification (M)
- Generate Tauri update keypair (`tauri signer generate`); private key only in CI secrets, **public key in `tauri.conf.json`**.
- Enable `plugins::updater` with the release endpoint (`https://github.com/.../releases/latest/download/latest.json`).
- CI: publish `latest.json` + signed zips per platform in the release job.
- UX: check on startup + a "بررسی به‌روزرسانی" item; updates install on next launch. Never auto-restart mid-recording (guard on `isRecording`).
- Acceptance: a patched build updates itself; a tampered zip is rejected by signature check (test with a corrupted artifact).

### 1.3 Promote dependency audits to hard gates (S)
- In `ci.yml`: make `npm audit` (high+), `pip-audit`, `cargo audit` fail the job (the audit found them effectively informational). Keep a documented override file for accepted risks.
- Acceptance: a vulnerable pinned dep breaks CI.

### 1.4 Release-build hardening (S)
- Ignore `PHLOX_DEV_BOOT` unless built with a debug/`dev` profile flag (compile-time `cfg!` or build-arg), so the auth bypass can never be toggled on packaged desktop builds.
- Set explicit permissions on the data dir and `phlox-app.log` (`0700`/`0600` on Unix) at creation — the log may still contain operational detail even after token redaction (F-01).
- Acceptance: unit/integration test that `PHLOX_DEV_BOOT=1` does **not** skip auth in release mode.

### 1.5 Provenance + checksums (S)
- Add `actions/attest-build-provenance` for every release artifact.
- Publish `SHA256SUMS` alongside each release asset (desktop installers are no longer published; the container image in `ghcr.io` is the only shipped artifact).
- Acceptance: every release asset has an attestation + a checksum line.

---

## 4. Phase 2 — Make installs fast

### 2.1 Size budget for the Python server (M)
- The Nuitka standalone dir is the biggest lever. Audit and trim:
  - `--nofollow-import-to` for modules the simplified app no longer needs (already done for `server.tests` — extend to anything importable-but-dead).
  - Exclude unused heavy optional deps from the `asr`/provider extras where the desktop path doesn't need them (e.g., unused SDK transports).
  - Strip native libraries where platform policy allows (never after signing — Windows Authenticode signs the final bytes, so strip **before** signing or not at all).
- Budget proposal: installer ≤ **350 MB** today is typical for llama.cpp-class apps; set an explicit target (e.g., ≤ 300 MB) and fail CI if exceeded (upload step compares to budget).
- Acceptance: measured size delta committed to this doc; CI size-gate.

### 2.2 Installer compression & channel selection (S)
- Windows: Tauri NSIS default uses LZMA — verify `bundle.windows.nsis.compression: "lzma"` explicitly.
- Windows is the only installer channel left: verify `bundle.windows.nsis.compression: "lzma"` explicitly.
- Acceptance: no regression in install time; sizes in baseline table.

### 2.3 Faster first run (M)
- Sidecars already warm-start; additionally:
  - Start llama + whisper **in parallel** during the startup loader (they are independent processes).
  - Keep the UI interactive immediately; gate only the *action* that needs a missing engine (the workspace already shows readiness panels — preserve that).
  - Cache model download metadata; skip "available models" network calls when a model is already selected and present.
- Acceptance: cold start → transcription-ready time improved vs Phase 0 baseline (target: −25%).

### 2.4 Model download resume (M)
- Today an interrupted multi-GB download restarts from zero (we unlink partials on cancel by design). Add **opt-in resume**: download to `<name>.part`, keep it on *network failure* (not on user cancel), send `Range:` on retry.
- Acceptance: kill the app at 50% of a model download → restart resumes from ~50% (logged), manual cancel still deletes.

---

## 5. Phase 3 — Make installs full (platform coverage)

### 3.1 Ship the Windows installer in CI (L)
macOS and Linux installers are no longer built or published, so the desktop target is Windows only:

| Platform | Artifact | Signing |
|---|---|---|
| Windows x86_64 | NSIS (+ zip for updater) | Phase 1.1 |
| Linux / macOS | none — Docker image only | n/a |

- Add a `windows-latest` job that runs `build-all.sh` + `tauri build` on a native runner; cache compiled sidecars by `(repo, commit, triple)` so PR builds stay fast.
- Acceptance: a tagged release produces the Windows installer, attested; updater `latest.json` lists it. Distribution on macOS/Linux stays the Docker image.

### 3.2 First-run completeness checklist (S)
- Keep the current gate flow (encryption → server startup → readiness panels). Add a single "آماده‌سازی" checklist card on the workspace when engines are missing, with one button per missing piece (download model / open settings). Mostly present today — make it explicit and track completion.
- Acceptance: a fresh install can reach "first transcription" without visiting settings more than once.

### 3.3 Optional offline model pack (M) — for clinics/air-gapped use
- Do **not** bloat the default installer with models (kills the "fast" goal).
- Ship an optional `phlox-models-<version>.zip` release asset: recommended LLM GGUF + recommended ASR model + manifest with SHA256 per file.
- App-side: "Import model pack" in the local-model manager → verifies manifest hashes → installs into the models dir → activates (reusing the existing selection files).
- Acceptance: on an offline machine, importing the pack yields a fully working app; a corrupted file is rejected by hash.

---

## 6. Phase 4 — Keep it full over time

- **Auto-update rollout** (Phase 1.2) is the long-term mechanism for the Windows desktop build: release notes in Persian, staged rollout via GitHub release (draft → publish).
- **Nightly channel already exists** (`nightly.yml`) — point power users there; keep stable channel for clinics.
- **Repair story**: uninstall/reinstall never touches `<data_dir>/Phlox` (already true by construction) — document it in README + in-app FAQ so users trust reinstalls.
- **Diagnostics**: "کپی اطلاعات تشخیص" button (versions, sidecar status, last audit-line count, redacted log tail) to make support fast without leaking PHI.

---

## 7. Ordering & effort summary

| # | Item | Goal | Effort | Depends on |
|---|---|---|---|---|
| 0 | Baseline measurements | all | S | — |
| 1.1 | Windows signing | secure | M | certificate purchase |
| 1.2 | Updater + keys | full, fast | M | — |
| 1.3 | Audits gate CI | secure | S | — |
| 1.4 | Dev-boot hardening, file perms | secure | S | — |
| 1.5 | Attestations + checksums | secure | S | — |
| 2.1 | Nuitka size audit + budget | fast | M | 0 |
| 2.2 | Compression settings | fast | S | — |
| 2.3 | Parallel sidecar start, lean startup calls | fast | M | 0 |
| 2.4 | Download resume | fast, full | M | — |
| 3.1 | Full platform matrix | full | L | 1.1 |
| 3.2 | Readiness checklist | full | S | — |
| 3.3 | Offline model pack | full | M | 3.1 |
| 4.x | Rollout/diagnostics/repair docs | full | S | 1.2 |

Recommended sequence: **0 → 1.3/1.4/1.5 (same week) → 1.2 → 2.1/2.3 → 1.1 + 3.1 → 2.4 → 3.3 → 3.2/4.x**.

---

## 8. Risks & guardrails (patient-data context)

1. **Never bundle PHI-adjacent material** into installers or update packages; model packs contain weights + manifest only.
2. **UPX is a no-go**: it triggers AV false positives on Windows and gives little on already-compressed installers.
3. **Signing identity handling**: certificates only in CI secret stores; never in repo or logs.
4. **Updater key loss = update channel death** — back up the private key offline (sealed), and document recovery (new key requires shipping the new public key in a manual release first).
5. **Don't change DB key handling or encryption flows** as part of packaging work (invariant 3) — packaging touches only binaries, resources, and installers.
6. **Size gates must not silently drop files**: fail the build loudly if the budget is exceeded, rather than auto-excluding something the server imports at runtime.
7. **Desktop distribution is Windows-only** now that the macOS/Flatpak installers are gone; keep the Docker image at feature parity so macOS/Linux users are not second-class (no setuid, no system-wide writes).
