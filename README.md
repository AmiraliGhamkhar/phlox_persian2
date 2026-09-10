# Phlox — Persian Medical AI Assistant

Phlox is a free, open-source medical assistant for Persian-speaking clinicians.

It converts clinical speech into text and generates structured medical reports using AI.

The app is designed with a **local-first** approach, so you can run AI models on your own PC.

## Main Features

* **Persian speech-to-text** — live transcription and dictation
* **Structured medical reports** — history, examination, assessment, and plan
* **Specialty-aware reports** — optimized for different medical specialties
* **Persian/English medical dictionary** — 5,000+ medical terms
* **Local AI models** — Whisper, Shenava, llama.cpp, etc.
* **Cloud AI support** — OpenAI, Anthropic, Groq, OpenRouter, Fireworks, Speechmatics, AssemblyAI, and more
* **Privacy-focused** — local mode keeps data on your PC
* **Docker support** — run the full application in a container

> **Warning:** Phlox is an experimental project for education and personal use. It is not an approved medical device and must not be used for clinical decision-making without professional review.

---

# Windows Setup

## Requirements

Install these first:

* Windows 10/11
* Docker Desktop
* Git
* Node.js 20+
* PowerShell 5.1+ or PowerShell 7+
* Python 3.11+

Check your installation:

```powershell
docker --version
git --version
node --version
npm --version
python --version
```

---

# Run with Docker

Clone the repository:

```powershell
git clone https://github.com/AmiraliGhamkhar/phlox_persian2.git
cd phlox_persian2
```

Create the environment file:

```powershell
Copy-Item .env.example .env
```

Generate a database encryption key:

```powershell
$key = -join ((1..64) | ForEach-Object {
    '{0:x}' -f (Get-Random -Maximum 16)
})

$key
```

Open `.env`:

```powershell
notepad .env
```

Set:

```env
DB_ENCRYPTION_KEY=your-key-here
```

Then start the application:

```powershell
docker compose up -d --build
```

Check the containers:

```powershell
docker compose ps
```

View logs:

```powershell
docker compose logs -f
```

Open the app:

```text
http://localhost:5000
```

Stop the app:

```powershell
docker compose down
```

---

# Online-Only Docker Setup

Use this option when you do **not** need local `llama.cpp` or `whisper.cpp`.

Build the smaller image:

```powershell
docker build -f Dockerfile.online -t phlox-online:latest .
```

Run it:

```powershell
docker run --rm -p 127.0.0.1:5000:5000 `
  -e DB_ENCRYPTION_KEY="your-key-here" `
  -v phlox_data:/usr/src/app/data `
  phlox-online:latest
```

The app will be available at:

```text
http://localhost:5000
```

---

# Local AI Models

Phlox supports local models for both speech recognition and text generation.

## Speech Recognition

Available options include:

* Whisper large-v3-turbo
* Shenava-Koochik
* Parakeet

For Persian, **Whisper** and **Shenava** are the main choices.

Configure them from:

```text
Settings → Model → Speech Recognition
```

## LLM

Supported providers include:

* llama.cpp
* Ollama
* LM Studio
* llama.cpp server
* 9Router / OmniRoute
* OpenAI
* Anthropic
* Fireworks
* Groq
* OpenRouter
* Other OpenAI-compatible APIs

Configure them from:

```text
Settings → Model → Language Model
```

---

# API Keys

API keys should never be stored in source code or committed to Git.

Configure them through the application settings or environment variables.

Supported cloud services include:

* OpenAI
* Anthropic
* Groq
* OpenRouter
* Fireworks
* Speechmatics
* AssemblyAI

---

# Development on Windows

Install frontend dependencies:

```powershell
npm ci
```

Start the frontend:

```powershell
npm run dev
```

Run frontend checks:

```powershell
npm run typecheck
npm run lint
npm test -- --run
```

Run backend checks:

```powershell
cd server
uv run ruff check .
uv run ruff format --check .
```

Run Python tests:

```powershell
$env:DB_ENCRYPTION_KEY="local-test-key"
uv run pytest -q
```

---

# Architecture

```text
React / Tauri
      ↓
FastAPI
      ↓
Application Services
      ↓
Provider Adapters
      ↓
 ┌───────────────┬───────────────┐
 │      LLM      │      ASR      │
 │               │               │
 │ llama.cpp     │ Whisper       │
 │ Ollama        │ Shenava       │
 │ LM Studio     │ Parakeet      │
 │ OpenAI        │ OpenAI Audio  │
 │ Anthropic     │ Speechmatics  │
 └───────────────┴───────────────┘
      ↓
   SQLCipher
```

The frontend does **not** call AI providers directly.

All requests go through the FastAPI backend, which handles:

* Authentication
* Validation
* AI provider selection
* Transcription
* Report generation
* Encrypted settings
* Database access

---

# Data and Privacy

Local mode keeps audio, text, reports, and models on your computer.

The database uses **SQLCipher** for encryption.

API keys are stored securely and are masked when displayed.

The application also includes protection for:

* CORS
* Host validation
* SSRF
* Request limits
* File upload limits
* Proxy headers

---

# Important Docker Notes

The database encryption key is required.

Do **not** change `DB_ENCRYPTION_KEY` after the database has been created unless you know how to migrate the encrypted data.

Docker stores application data in:

```text
/usr/src/app/data
```

The default Docker setup uses:

```text
phlox_data
```

as the persistent volume.

---

# Project Status

Phlox is still experimental.

AI-generated medical text can be wrong. Always review the transcription and generated report before using it.

Phlox is currently intended for:

* Education
* Research
* Personal use
* Development and testing

It is **not** intended to replace professional medical judgment.

---

# License

MIT License.

See:

```text
LICENSE
```

For third-party model and dependency information, see the project documentation.

# Contributing

Pull requests and contributions are welcome.

Before submitting changes, review:

* Code quality
* Privacy
* Security
* Clinical data safety

Repository:

https://github.com/AmiraliGhamkhar/phlox_persian2
