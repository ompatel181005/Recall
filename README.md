# TranscribeAI

Record your lectures, transcribe them locally on your GPU, and let AI turn them
into notes, a course tutor, quizzes, and flashcards. Single-user local web app:
FastAPI backend + React frontend, open it from your laptop or your phone on the
same Wi-Fi.

- Product spec: [docs/SPEC.md](docs/SPEC.md)
- Milestones: [docs/ROADMAP.md](docs/ROADMAP.md)

## Setup

Prereqs: Python 3.13+, Node 20+, Git. Optional but recommended: NVIDIA driver
with CUDA (for GPU transcription), [Ollama](https://ollama.com) running locally
(for free local LLM tasks — `ollama pull qwen2.5:7b nomic-embed-text`), and
ffmpeg on PATH (for importing video/odd audio formats, needed from M1).

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

Open http://localhost:5173. The header shows backend/provider status from
`/api/health`.

## Configuration

`config.yaml` routes every AI task to a provider and model — switch any task
between local (Ollama) and cloud (Claude or any OpenAI-compatible API) by
editing that file. Transcription model/device also lives there. API keys go in
`.env` (see `.env.example`).

## Notes

- Whisper models download on first transcription (M1), not at install time.
- If `nvidia-smi` works but transcription falls back to CPU, check that the
  installed ctranslate2 wheel matches your CUDA runtime (see faster-whisper
  docs).
- All recordings, slides, and the database live under `data/` and are never
  committed.
