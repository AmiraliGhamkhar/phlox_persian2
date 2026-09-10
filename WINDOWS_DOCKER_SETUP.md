# Phlox — Running on Windows 11 with Docker

> This file was written for the repository **`phlox_persian2`** (branch `arena/01a08502-phlox-persian2`, version 2.2.4, commit `0583585`).
> It contains (1) a full analysis of every folder/file/Dockerfile in the repo, and (2) exact, tested instructions to run Phlox on **Windows 11 + Docker Desktop**.
> A condensed فارسی (Persian) version of the run steps is at the end.

---

## 1. What Phlox is

**Phlox (فلوکس)** is an open-source, MIT-licensed, *Persian-first* medical assistant: it transcribes doctor–patient visits to text (ASR) and then produces a structured **Persian clinical report** (chief complaint, history, exam, assessment, plan) with an LLM. It is a **local-first** app: audio and text stay on your machine when you use local models. The whole UI is Persian/RTL.

Important legal note from the project: it is **experimental, not a certified medical device**, and not for production/clinical decision-making without your own compliance work (HIPAA/GDPR etc.). It shows this warning on first launch.

The web/Docker build is a **single container** that serves both the compiled React UI and the FastAPI backend on one port (5000). The desktop Tauri build (`src-tauri/`) is a separate shell around the same code — you do **not** need it for Docker.

---

## 2. Repository analysis (folders, files, code)

### 2.1 Root-level files

| File | Purpose |
|---|---|
| `README.md` | Full Persian documentation (features, architecture, security, usage warning). |
| `CHANGELOG.md` | Release history. |
| `package.json` | Frontend: React 19 + Chakra UI, Vite 8, Node ≥24 (<25), npm 11.16. Scripts: `npm run dev`, `build`, `tauri-build`, tests (vitest). |
| `package-lock.json` / `.npmrc` / `.nvmrc` | npm lockfile; `.npmrc` pins `ignore-scripts=true` + release-age cooldown; `.nvmrc` = Node 24. |
| `vite.config.js` | Vite: React plugin, output `build/`, dev server **port 3000** on 0.0.0.0, proxies `/api` → `http://localhost:5000` (ws too), `allowedHosts: true`. |
| `index.html` | `lang="fa-IR" dir="rtl"`, Vazirmatn fonts, title «فلوکس \| Phlox». |
| `tsconfig.json`, `eslint.config.js` | TS check + ESLint config. |
| `Makefile` | Helper targets incl. `docker-up`, `docker-build`, `rebuild-prod/dev/test`, `docker-dev-up`. |
| `Dockerfile` | **Production image** (3 stages, analyzed in §3.1). |
| `Dockerfile.online` | **Online-only image**: same as `Dockerfile` but skips the llama.cpp/whisper.cpp compile and the ONNX `asr` extra — for cloud providers / host-side model servers only. Builds fast, smaller image. |
| `Dockerfile.dev` | **Development image** with hot reload (analyzed in §3.2). |
| `Dockerfile.test` | Runs the pytest suite inside an image (used by CI). |
| `docker-compose.yml` | **Production stack** (analyzed in §3.3). |
| `docker-compose.dev.yml` | Dev stack: UI `:3000` + API `:5000`, whole repo bind-mounted. |
| `.env.example` | Template for `.env` — copy and set `DB_ENCRYPTION_KEY` (required). |
| `.dockerignore` | Keeps `.env`, `data/`, `src-tauri/`, `node_modules`, `.git` etc. out of the image. |
| `.gitattributes` | **Important for Windows**: forces `LF` line endings for `Dockerfile*`, `*.sh`, `.env.example`, `docker-compose*.yml` — CRLF would break the shell entrypoints and the encryption key parsing. |
| `build-all.sh` | Desktop build orchestration (not used in Docker). |
| `assets/` | Icon + README screenshot. |
| `.github/workflows/` | CI (lint, tests incl. Docker test), build/release (**docker image → `ghcr.io`**), nightly image build, codeql, dependabot. |

### 2.2 `server/` — Python backend (FastAPI, Python ≥3.12, uv-locked)

| Path | Contents |
|---|---|
| `server/server.py` | App entry point (`python -m server.server`); uvicorn, middleware stack (CORS same-origin by default, Host validation / DNS-rebinding defence, rate limiting, body-size caps, SSRF guard, proxy-auth), static SPA serving from `build/`, API routers, scheduler. |
| `server/constants.py` | Environment handling: `IS_DOCKER` (detects `/.dockerenv` or `DOCKER_CONTAINER=true`) → data at `/usr/src/app/data`, build at `/usr/src/app/build`, temp at `/usr/src/app/temp`. |
| `server/api/` | REST routers: `config/` (global, models, local models, providers/whisper model catalogs, system, user, validation), `transcribe.py`, `workspace.py` (patients/notes), `dashboard.py` (incl. `/api/dashboard/health` used by the container HEALTHCHECK). |
| `server/database/` | **SQLCipher**-encrypted SQLite (`phlox_database.sqlite`), singleton connection, backups before migration, 10 versioned migrations (`v1_initial_schema` … `v10_ai_providers`), config defaults/prompts. Key from env `DB_ENCRYPTION_KEY` or `/run/secrets/db_encryption_key`. |
| `server/llm_client/` | LLM adapters: OpenAI-compatible + Anthropic providers (client, providers/, utils). |
| `server/transcription/` | ASR: `live.py` (Speechmatics realtime WS), `assemblyai.py`, `speechmatics_protocol.py`, `parakeet.py`, `asr_context.py`, `audio.py`, `language.py`, `hygiene.py`, whisper-server client. |
| `server/nlp_tools/` | Report structuring + specialty tuning. |
| `server/data/terms/` | **20+ JSON Persian↔English medical dictionaries** (anatomy, symptoms, medications, labs, oncology, obstetrics, procedures, … >5000 terms), plus `medical_dictionary.py`, validator `validate_terms.py`. |
| `server/utils/` | `local_servers.py` (the API **supervises the bundled llama-server/whisper-server binaries** in Docker), `local_autoconfig.py`, `llama_models.py`, `whisper_models.py`, `allocated_ports.py`, `http_retry.py`, `parent_watchdog.py`, `request_limits.py`, `ssrf.py`, … |
| `server/tests/` | ~17 test modules (pytest + asyncio), incl. ASR language matrix, API error contract, database, providers. |
| `server/pyproject.toml` + `uv.lock` | Pinned deps: fastapi, uvicorn, sqlcipher3, openai, httpx, speechmatics-rt, onnxruntime+numpy (`asr` extra), … |
| `.python-version`, `_version.py` | 3.12; version 2.2.4. |

### 2.3 `src/` — Frontend (React 19 + Chakra UI, Persian/RTL)

- `src/App.jsx`, `src/index.jsx`, `theme/` (RTL Chakra theme), `i18n/`.
- **Three pages** (`src/pages/`): `SpecialtyPage.jsx` (pick specialty), `WorkspacePage.jsx` (record/transcribe → structured report), `Settings.jsx` (LLM + ASR providers, local model downloads).
- `src/components/settings/` — `LocalModelManager.jsx`, `LlmTab.jsx`, `ModelSettingsPanel.jsx`, `WhisperTab.jsx` (one-click local model download & engine start).
- `src/components/setup/` — first-run encryption/passphrase setup (desktop flow).
- `src/utils/` — API clients (`api/`: `transcriptionApi.ts`, `workspaceApi.ts`, `settingsApi.ts`, `localModelApi.ts`, `encryptionApi.ts`, `sseStream.ts`), **`helpers/apiConfig`**: in a browser/Docker it calls **relative same-origin `/api` URLs** (no token); in Tauri it targets `localhost:5000` with a request token. `audioRecorder.js`, hooks, services (`localModelService.ts`).
- `public/` — Vazirmatn fonts (Persian woff2), icons, `site.webmanifest`.

### 2.4 `src-tauri/` — desktop shell (Tauri 2 + Rust)

Not needed for Docker (and explicitly excluded by `.dockerignore`). It holds the desktop app, plus build scripts that compile `llama.cpp` / `whisper.cpp` / `parakeet.cpp` engines from source with pinned SHAs — the **same engines the Docker image compiles** in its stage 2.

### 2.5 Other

- `scripts/` — `expand_dictionary.py` (term dictionary generator) and `live_asr_smoke_test.py` (tests a Speechmatics realtime session with a real key).

---

## 3. Docker analysis

### 3.1 `Dockerfile` (production) — 3 stages

1. **Stage 1 `build`** (`node:24-slim`): `npm ci`, `npm run build` → static SPA in `build/`.
2. **Stage 2 `local-runtime`** (`debian:bookworm-slim`): compiles from source, CPU-only:
   - `llama.cpp` @ pinned SHA → `llama-server` (bundled as `phlox-llama-server`)
   - `whisper.cpp` @ pinned SHA → `whisper-server` (bundled as `phlox-whisper-server`)
   - ⚠️ *This stage needs network (GitHub clone) at first build and takes the longest.*
3. **Stage 3 runtime** (`python:3.12-slim`):
   - Copies uv (pinned digest), installs apt `ca-certificates`+`tzdata`, copies the two engine binaries to `/usr/local/bin`.
   - `uv sync --locked --no-dev --extra asr` → venv at `server/.venv` with **onnxruntime/numpy** so Shenava & Parakeet (ONNX) models run in-process.
   - Env: `DOCKER_CONTAINER=true`, `PATH`/`PYTHONPATH`, `SERVER_HOST=0.0.0.0`, `PORT=5000`.
   - Creates unprivileged user `phlox` (**uid/gid 1000**), dirs `data/` + `temp/` owned by it.
   - `HEALTHCHECK` → python stdlib GET `/api/dashboard/health` (401/403 count as healthy).
   - `STOPSIGNAL SIGTERM`; `CMD ["python", "-m", "server.server"]` → serves API **and** SPA on port **5000**.

### 3.2 `Dockerfile.dev`

Node toolchain + Python in one dev image; `start-phlox-dev.sh` runs `vite` (:3000) and `uvicorn --reload --reload-dir server` (:5000) via GNU parallel. Used only with `docker-compose.dev.yml`.

### 3.3 `docker-compose.yml` (production)

- Service `app`, container `phlox`, project `phlox`.
- `image: ${PHLOX_IMAGE:-ghcr.io/amiralighamkhar/phlox_persian2:latest}` **and** a `build:` block — `docker compose up -d --build` builds locally from this repo; with plain `docker compose up -d` it pulls the published image (if it exists for the given tag; the fallback that always works is the local build).
- Ports: **`127.0.0.1:${PHLOX_PORT:-5000}:5000`** — loopback only (good for local Windows use; no proxy auth needed).
- `extra_hosts: host.docker.internal:host-gateway` → inside the container you can reach an LLM/ASR server running **on your Windows host** (Ollama, LM Studio…) at `http://host.docker.internal:11434`.
- Environment from `.env`: **`DB_ENCRYPTION_KEY` is mandatory** (compose refuses to start without it), plus optional `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `TRUSTED_PROXY_CIDRS`, `TZ`, `RATE_LIMIT_ENABLED`, `LLM_EXTRA_BODY`, proxy-auth vars, ASR live tuning vars.
- Volumes: named volume **`phlox_data` → `/usr/src/app/data`** (encrypted DB + downloaded local models + reports). Commented bind-mount alternative.
- Hardening: `init: true`, `no-new-privileges`, `cap_drop: ALL`, log rotation, healthcheck (interval 30 s).

### 3.4 Data flow

```
Browser (Windows) → http://127.0.0.1:5000
  → FastAPI /api (same-origin SPA served by the container)
  → domain services → provider adapters
  → local (bundled llama-server / whisper-server / ONNX Shenava–Parakeet)
    or cloud (OpenAI / Anthropic / Groq / Fireworks / OpenRouter / Speechmatics / AssemblyAI)
  → SQLCipher DB + JSON medical dictionaries, all under /usr/src/app/data (volume)
```

---

## 4. Running on Windows 11 + Docker — step by step

### 4.0 Prerequisites

1. **Windows 11** (Home or Pro). 
2. **Docker Desktop for Windows** installed and running, with the **WSL 2 backend** (default on modern installs). Enable it during install / in *Settings → General → Use WSL 2 based engine*. Virtualization must be on in BIOS/UEFI.
   - Installer: https://docs.docker.com/desktop/install/windows/
3. **Resource settings**: Docker Desktop → *Settings → Resources → Advanced*. The default **2 GB WSL memory is too small** for local models. Recommended: **≥ 8 GB RAM** (up to half your machine’s RAM, e.g. 8–16 GB) and **4+ CPUs** if you plan to run Whisper/lama.cpp locally inside the container. You can also just use *cloud* providers from the app without local models — then defaults are fine.
4. Disk: the first local build downloads/compiles several GB; leave **≥ 15 GB free**. The running container + data volume is a few GB more.
5. (Recommended) Git for Windows or another `openssl`; not strictly required — see §4.3 for a PowerShell key generator.
6. Make sure nothing else uses **port 5000** (see §6 if it does).

### 4.1 Get the code

```powershell
# Option A: clone (fresh)
git clone https://github.com/AmiraliGhamkhar/phlox_persian2.git
cd phlox_persian2

# Option B: you already have this folder — open a terminal in it.
```

> `.gitattributes` in this repo forces LF line endings on checkout, which keeps Dockerfiles, shell scripts and `.env.example` container-safe on Windows. If you ever *create* `.env` with Notepad, make sure it stays LF (`git` users: set `core.autocrlf` appropriately; VS Code: “LF” in the status bar).

### 4.2 Create `.env`

```powershell
Copy-Item .env.example .env
```

### 4.3 Set the required encryption key

The key encrypts the SQLCipher database. **It cannot be changed later** without losing access to your data — save it somewhere safe.

Generate a 64-hex-char key with **either**:

```powershell
# PowerShell (any machine, no openssl needed):
$b = New-Object byte[] 32; [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ([System.BitConverter]::ToString($b)).Replace('-','').ToLower()
```

```bash
# or Git Bash / any openssl:
openssl rand -hex 32
```

Then open `.env` and paste it on the `DB_ENCRYPTION_KEY=` line, e.g.:

```env
DB_ENCRYPTION_KEY=9f2c…(64 hex chars)…
```

> 🚀 Easiest: run the bundled helper script `run-on-windows.ps1` (§4.7) — it creates `.env`, generates and inserts the key for you, prints it once, then starts everything.
> Options you can leave at defaults: `PHLOX_PORT=5000`, `TZ=Etc/UTC` (or `Asia/Tehran`), `RATE_LIMIT_ENABLED=true`, everything else empty.

### 4.4 Build & start the container

From the repo root:

```powershell
docker compose up -d --build
```

What happens:

- Docker builds the 3-stage image locally (first time: **10–40 min** depending on CPU — it compiles llama.cpp and whisper.cpp; later runs are instant).
- Starts container `phlox`; healthcheck pings `/api/dashboard/health`.

Watch it:

```powershell
docker compose ps            # expect STATUS: Up … (healthy)
docker compose logs -f       # Ctrl+C to stop following
```

If you do **not** want to build and a published image is available for your tag, you can instead run:

```powershell
# Only if ghcr.io/amiralighamkhar/<your-repo>:latest exists; otherwise this fails → use the build above.
docker compose pull
docker compose up -d
```

(`docker-compose.yml` builds locally by default when the image isn’t pulled — `up -d --build` always works.)

### 4.5 Open Phlox

- **UI:** http://127.0.0.1:5000 — (use `127.0.0.1`, it counts as a “secure context”, so **microphone access works**; plain `localhost` works too).
- **API docs (Swagger):** http://127.0.0.1:5000/docs
- **Health:** http://127.0.0.1:5000/api/dashboard/health → `{"status": "ok", …}`

First run:

1. Read the Persian usage warning and accept.
2. Pick your specialty.
3. Go to **تنظیمات (Settings) → مدل (Model)**:
   - **Cloud**: choose OpenAI / Anthropic / Groq / Fireworks / OpenRouter / Ollama… and paste an API key (stored encrypted in the DB).
   - **Ollama/LM Studio on your Windows host**: use `http://host.docker.internal:11434` as the base URL — the compose file already maps that hostname.
   - **Local inside Docker**: Settings → Model → Local → download a speech model (Whisper `large-v3-turbo` Q6_K GGUF ≈ recommended; F16/Q5_0/Q8_0 GGML also listed). The bundled `llama-server`/`whisper-server` start automatically; Shenava (Persian, Reza2kn tract-streaming INT4) & Parakeet run in-process (ONNX). Models are stored on the `phlox_data` volume, so they survive restarts.

### 4.6 Stop / start / upgrade

```powershell
docker compose stop      # pause
docker compose start     # resume
docker compose down      # stop + remove container (data volume KEPT)
docker compose up -d --build   # after pulling new code: rebuild + update
```

Your data (encrypted DB, settings, reports, downloaded models) lives in the named volume **`phlox_phlox_data`** (the compose project is `phlox`, so Docker prefixes the volume declared as `phlox_data`) and survives `down`/`up`. Confirm with `docker volume ls`.

### 4.7 One-shot helper script (recommended)

The repository includes `run-on-windows.ps1`. In PowerShell, from the repo root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass          # allow this session only
.\run-on-windows.ps1                                # build, run, wait for healthy, open browser
.\run-on-windows.ps1 -UsePublishedImage             # docker compose pull instead of build
.\run-on-windows.ps1 -Dev                            # hot-reload dev stack (UI :3000, API :5000)
```

---

## 5. Development on Windows (optional)

```powershell
docker compose -f docker-compose.dev.yml up --build
# UI  → http://localhost:3000  (Vite, proxies /api to :5000)
# API → http://localhost:5000/docs
```

Notes:

- Whole repo is bind-mounted; edits to `server/` restart uvicorn, edits to `src/` hot-reload.
- File watching over bind mounts is unreliable on Windows — if HMR stops, enable polling in `vite.config.js`: `server: { watch: { usePolling: true } }` (the compose file comments this too).
- `docker-compose.dev.yml` maps ports on all interfaces and uses a throwaway default key (`phlox-dev-insecure-key`); fine for local dev only.
- Don’t run the dev and prod stacks at the same time (container names `phlox-dev` / `phlox` are fixed).

---

## 6. Troubleshooting on Windows 11

| Symptom | Cause / fix |
|---|---|
| `docker: 'compose' is not a docker command` | Docker Desktop too old or compose v2 disabled → update Docker Desktop. |
| `Set DB_ENCRYPTION_KEY in .env …` and the stack refuses to start | Key missing/empty in `.env`. Generate one (§4.3). |
| Container starts then exits, logs show `Cannot decrypt existing database` | The `.env` key differs from the key the volume was first created with, or a CRLF ended up in the key. If you have the old key, restore it; otherwise the volume can’t be decrypted — only `docker compose down -v` (deletes data!) would allow a fresh start. |
| Port 5000 busy | Change the host port in `.env`: `PHLOX_PORT=5001`, then `docker compose up -d`. Open http://127.0.0.1:5001. |
| Build fails at `git clone … llama.cpp` / `whisper.cpp` | Transient network/proxy issue — rerun `docker compose up -d --build`. Corporate proxies may need Docker Desktop proxy settings. |
| Very slow first build | Expected: it compiles two C++ inference engines. Only once (cached afterwards). |
| Mic does not work / not available in browser | Use http://127.0.0.1:5000 (loopback = secure context). Check Windows privacy: Settings → Privacy → Microphone → allow apps/browsers. |
| “Out of memory” when downloading local models | Increase Docker Desktop RAM (Resources → Advanced) to ≥8 GB. |
| Can’t reach Ollama on the host from Settings | Use `http://host.docker.internal:11434` and make Ollama listen on 0.0.0.0 (its default does). |
| UI loads but API calls fail (dev stack) | Ensure Vite proxy target works; in the dev stack the UI is :3000, API :5000. |
| Want a fresh start / clean everything | ⚠️ Deletes data: `docker compose down -v && docker compose rm -f`. |

### Backup / restore the data volume

The named volume is `phlox_phlox_data` (see §4.6). From PowerShell:

```powershell
docker run --rm -v phlox_phlox_data:/data -v "${PWD}:/backup" alpine tar czf /backup/phlox-data-backup.tar.gz -C /data .
# restore (⚠️ overwrites current data):
docker run --rm -v phlox_phlox_data:/data -v "${PWD}:/backup" alpine sh -c "rm -rf /data/* && tar xzf /backup/phlox-data-backup.tar.gz -C /data"
docker compose restart
```

If `docker volume ls` shows a different name (older compose), use that name in the commands above.

---

## 7. خلاصهٔ فارسی — اجرا در ویندوز ۱۱ با داکر

**فلوکس** یک دستیار گزارش‌نویسی پزشکی فارسی است: گفتار ویزیت را به متن (ASR) و سپس به گزارش بالینی ساختاریافته (LLM) تبدیل می‌کند. در نسخهٔ داکر، یک کانتینر هم رابط کاربری و هم API را روی پورت `5000` سرو می‌کند. ساختار مخزن: `server/` بک‌اند FastAPI + پایگاه‌دادهٔ رمزنگاری‌شدهٔ SQLCipher، `src/` رابط کاربری React فارسی/راست‌به‌چپ، `src-tauri/` نسخهٔ دسکتاپ (برای داکر لازم نیست)، `Dockerfile` سه‌مرحله‌ای (ساخت React، کامپایل llama.cpp/whisper.cpp، اجرای Python)، و `docker-compose.yml` برای اجرای آماده.

مراحل اجرا در ویندوز ۱۱:

1. **Docker Desktop** را با بک‌اند **WSL 2** نصب و اجرا کنید (در تنظیمات Docker حداقل ۸ گیگابایت RAM بدهید).
2. کد را بگیرید و وارد پوشهٔ آن شوید: `git clone … phlox_persian2` سپس `cd phlox_persian2`.
3. فایل `.env` را بسازید: `Copy-Item .env.example .env` و حتماً متغیر اجباری `DB_ENCRYPTION_KEY` را پر کنید (یک کلید ۶۴ کاراکتری هگز: `openssl rand -hex 32` یا دستور PowerShell در بخش ۴.۳). کلید را جای امن ذخیره کنید؛ بعداً قابل تغییر نیست.
4. ساخت و اجرا: `docker compose up -d --build` (بار اول ۱۰ تا ۴۰ دقیقه برای کامپایل موتورهای محلی طول می‌کشد).
5. برنامه را در مرورگر باز کنید: `http://127.0.0.1:5000` (مستندات API: `/docs`).
6. در «تنظیمات ← مدل» سرویس ابری (کلید API) یا مدل محلی (دانلود داخل برنامه، ذخیره در volume) را انتخاب کنید؛ برای اتصال به اولاما/الاماستودیو روی خود ویندوز از `http://host.docker.internal:11434` استفاده کنید.
7. متوقف کردن: `docker compose down` — داده‌ها در volume به نام `phlox_phlox_data` می‌مانند (با `docker volume ls` ببینید).

فایل کمکی `run-on-windows.ps1` همهٔ این مراحل را خودکار انجام می‌دهد. عیب‌یابی رایج (پورت اشغال، کلید اشتباه، حافظهٔ داکر، میکروفون) در جدول بخش ۶ آمده است.

> ⚠️ این پروژه یک ابزار آزمایشی/آموزشی است و وسیلهٔ پزشکی تأییدشده نیست. داده‌ها و خروجی‌های هوش مصنوعی را مسئولانه مدیریت و بررسی کنید.
