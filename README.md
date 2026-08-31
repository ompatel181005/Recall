# TranscribeAI

Record your lectures, transcribe them locally on your GPU, and let AI turn them
into notes, a course tutor, quizzes, and flashcards. Single-user local web app:
FastAPI backend + React frontend, open it from your laptop or your phone on the
same Wi-Fi.

- Product spec: [docs/SPEC.md](docs/SPEC.md)
- Milestones: [docs/ROADMAP.md](docs/ROADMAP.md)

## Setup

Prereqs: Python 3.13+, Node 20+, Git, and **ffmpeg on PATH** (duration probing,
video→audio extraction, playback transcoding). Optional but recommended: an
NVIDIA GPU + driver (transcription falls back to CPU without one, much slower)
and [Ollama](https://ollama.com) running locally for free local LLM tasks
(`ollama pull qwen2.5:7b` and `ollama pull nomic-embed-text`).

```powershell
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -e .

# 2. Frontend
cd ..\frontend
npm install

# 3. Secrets (only for the cloud providers you use)
cd ..
copy .env.example .env   # then edit .env
```

## Run (development)

Two terminals:

```powershell
cd backend; .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd frontend; npm run dev
```

Open http://localhost:5173 (or the Wi-Fi address Vite prints, to record from
your phone). Add a course in the sidebar, then record or import a lecture —
transcription starts automatically and the transcript appears when it finishes.
"System status" at the bottom of the sidebar shows GPU/ffmpeg/provider health.

Browser recording needs a secure context. `localhost` counts; reaching the dev
server over LAN by IP does not, so mic capture from a phone needs HTTPS or
Chrome's "Insecure origins treated as secure" flag.

## Configuration

`config.yaml` routes every AI task to a provider and model — switch any task
between local (Ollama) and cloud (Claude or any OpenAI-compatible API) by
editing that file. Transcription model/device also lives there. API keys go in
`.env` (see `.env.example`).

## Notes

- Whisper models download from Hugging Face on first transcription (~1.5 GB for
  `distil-large-v3`), not at install time. The first run therefore looks slow.
- CUDA needs cuBLAS and cuDNN 9 at runtime. They install as the
  `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` dependencies, and
  `services/transcribe.py` puts their `site-packages` DLL folders on the search
  path at import — so no system PATH edits. If you ever see
  `Library cublas64_12.dll is not found`, those wheels are missing.
- Transcription runs one lecture at a time on a single background worker; extra
  lectures queue. `/api/lectures/{id}/job` reports progress.
- All recordings, slides, and the database live under `data/` and are never
  committed.
