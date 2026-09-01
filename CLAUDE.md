# TranscribeAI

Personal lecture-recording → transcription → AI study companion. Single user,
runs locally on a Windows 11 laptop (RTX 4060 8GB VRAM). Read
[docs/SPEC.md](docs/SPEC.md) for the full product spec and
[docs/ROADMAP.md](docs/ROADMAP.md) for milestones before building features.

**Current status: M2 (summaries & notes) done. Next milestone: M3 — Slides.**

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
  (summarize / chat / quiz / embeddings) to a provider (claude | openai |
  ollama) + model. Feature code asks
  `services/providers/registry.get_provider_for_task("summarize")` and calls
  `.complete(...)`. Adding a provider = new subclass of
  `LLMProvider` in `services/providers/` + registry entry.
- **Local-first bias.** Prefer free local models (Whisper, Ollama) when quality
  is acceptable; reserve cloud (Claude / OpenAI-compatible) for
  quality-critical tasks. Keep both paths working.
- Secrets live in `.env` (see `.env.example`), never in config.yaml or code.
- All user data (SQLite DB, audio, PDFs) lives under `data/` — gitignored;
  files on disk are referenced by path from the DB, never stored as blobs.
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
