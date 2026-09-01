# Recall

Personal lecture-recording → transcription → AI study companion. Single user,
runs locally on a Windows 11 laptop (RTX 4060 8GB VRAM). Read
[docs/SPEC.md](docs/SPEC.md) for the full product spec and
[docs/ROADMAP.md](docs/ROADMAP.md) for milestones before building features.

**Current status: M4 (Q&A tutor) done. Next milestone: M5 — Quizzes, Flashcards & Web Search.**

## Stack

- Backend: Python 3.13, FastAPI + uvicorn, SQLModel over SQLite, in `backend/`
  (venv at `backend/.venv`).
- Frontend: React + TypeScript + Vite in `frontend/`; dev server proxies `/api`
  to the backend on port 8000.
- Transcription: faster-whisper on CUDA (local, free). LLM tasks go through the
  provider layer — never call an SDK directly from feature code.
- ffmpeg must be on PATH (audio probing, video→audio, playback transcode).

## Core conventions

- **Provider routing is config, not code.** `config.yaml` maps each task
  (summarize / chat / quiz / embeddings) to a provider (claude | gemini |
  openai | ollama) + model. Feature code asks
  `services/providers/registry.get_provider_for_task("summarize")` and calls
  `.complete(...)`. Adding a provider = new subclass of
  `LLMProvider` in `services/providers/` + registry entry.
- **Local-first bias.** Prefer free local models (Whisper, Ollama) when quality
  is acceptable; reserve cloud (Claude / OpenAI-compatible) for
  quality-critical tasks. Keep both paths working.
- Secrets live in `.env` (gitignored), never in config.yaml, code, or a
  committed template. The variables are documented in README.md instead —
  there is intentionally no `.env.example` to paste a real key into.
- All user data (SQLite DB, audio, PDFs) lives under `data/` — gitignored;
  files on disk are referenced by path from the DB, never stored as blobs.
- **Recordings are irreplaceable.** A lecture captures a one-off event that
  cannot be re-recorded. Deleting one moves its audio and text to
  `data/.trash/` rather than destroying them; keep it that way.
- **Never run tests against the real `data/`.** Set `RECALL_DATA_DIR`
  to a scratch path first. Test code creates and deletes courses wholesale,
  and a cascade delete against real data destroys the user's lectures.
- API routes live under `/api/*` in `backend/app/routers/`; keep routers thin,
  logic in `backend/app/services/`.

## Running

- Backend: `backend\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000`
  (cwd `backend/`).
- Frontend: `npm run dev` (cwd `frontend/`), opens on port 5173.
- Health check: `GET http://localhost:8000/api/health` reports provider/CUDA
  availability.

## When building a milestone

1. Re-read its section in docs/ROADMAP.md; meet the **Accept** criterion.
2. Update the "Current status" line above when a milestone completes.
3. Heavy work (transcription, summarisation, embedding) must run as background
   jobs — never block a request handler on a model. `services/jobs.py` owns
   the workers: add a new kind to `LANE_FOR_KIND` and a handler in
   `_handler_for`, rather than spawning threads. The `gpu` lane is
   serialised; the `llm` lane runs alongside it.
