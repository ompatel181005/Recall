# TranscribeAI — Product Specification

## What this is

A personal, locally hosted web app for a university student that turns lecture
audio into searchable, teachable course material:

1. **Capture** — record lectures on the laptop mic in class, capture online
   lectures (system audio or the recording file), or import existing
   audio/video files.
2. **Transcribe** — after the lecture, convert speech to timestamped text
   locally on the GPU (no cloud, no cost, private).
3. **Learn** — AI generates structured notes and summaries, answers questions
   about the whole course (RAG over transcripts + slides), builds quizzes and
   flashcards, and can search the web to explain beyond what the lecturer said.
4. **Slides** — lecture slide PDFs attach to a lecture and become part of the
   AI's context.

## Non-goals (for now)

- Live/real-time transcription during the lecture (design must not preclude it).
- Multi-user accounts or cloud hosting — this is a single-user app on one laptop.
- Slide-to-transcript time alignment — slides are plain attached context.
- Mobile native app — the web UI reachable over LAN covers phone access.

## Users & environment

- Single user, Windows 11 laptop, RTX 4060 Laptop GPU (8GB VRAM), 16GB RAM.
- Ollama installed locally; Anthropic API key and an OpenAI-compatible key
  available.
- Guiding principle: **use free local open-source models wherever they are good
  enough; spend cloud tokens only where quality visibly matters.** Every AI
  task's provider is a config choice, not a code path.

## Domain model

```
Course        — name, code, term
└── Lecture   — title, date, status (recorded → transcribing → ready)
    ├── audio file        (data/audio/…)
    ├── Transcript        — segments [{start, end, text}], full text
    ├── SlideDeck 0..n    — PDF file + extracted text (data/slides/…)
    ├── Note 0..n         — AI-generated summaries/notes (markdown)
    └── (M4+) chunks/embeddings for RAG; (M5) quizzes, flashcards
```

Storage: SQLite (via SQLModel) for metadata, transcripts, notes; raw audio and
PDFs on disk under `data/`, referenced by path. Everything in `data/` is
gitignored.

## Architecture

- **Backend**: Python 3.13, FastAPI + uvicorn. Serves the JSON API under
  `/api/*` and (in production mode) the built frontend.
- **Frontend**: React + TypeScript + Vite SPA. Sidebar of courses → lectures;
  main pane shows transcript / notes / chat depending on milestone.
- **Transcription**: `faster-whisper` (CTranslate2) on CUDA. Default model
  `distil-large-v3`; configurable in `config.yaml`. Runs as a background job so
  the API stays responsive.
- **LLM provider layer** (`backend/app/services/providers/`):
  - `base.py` defines `LLMProvider.complete(messages, system, max_tokens, ...)`.
  - Implementations: `claude.py` (Anthropic SDK), `openai_compat.py` (OpenAI SDK
    pointed at any base URL), `ollama.py` (local HTTP API).
  - `registry.py` reads `config.yaml`'s `tasks:` section and returns the right
    provider+model for a named task (`summarize`, `chat`, `quiz`, `embeddings`).
- **Web search** (M5): Claude's built-in web-search tool when the task routes
  to Claude; SearXNG or DuckDuckGo scraping fallback for fully local mode.
- **Recording** (M1): browser `MediaRecorder`. Three sources — the microphone
  (with a device picker, so an OS loopback input like "Stereo Mix"/VB-Cable
  works too), tab/screen audio via `getDisplayMedia` for online lectures, or
  both mixed through a `WebAudio` graph. Existing recordings can be uploaded
  instead; ffmpeg extracts the audio track from video and produces a seekable
  MP3 for playback (browser WebM carries no duration header).
- **Background jobs** (`services/jobs.py`, M1): one daemon worker thread drains
  a queue so request handlers never block on the GPU and only one Whisper model
  is resident at a time. Progress is in-memory; lecture status and transcripts
  are in SQLite, so a restart costs only the percentage readout.

## API surface (grows per milestone)

- `GET  /api/health` — status + which providers are usable (key present,
  Ollama reachable, CUDA available).
- `GET|POST /api/courses`, `GET|PATCH|DELETE /api/courses/{id}` (M1) —
  deleting a course cascades to its lectures, transcripts and audio files.
- `GET|POST /api/lectures`, `GET|PATCH|DELETE /api/lectures/{id}` (M1);
  list filtered by `?course_id=`.
- `POST /api/lectures/{id}/audio` — multipart upload; stores the file, probes
  duration and queues transcription (M1).
- `GET  /api/lectures/{id}/audio` — serves the recording with Range support so
  the player can seek (M1).
- `POST /api/lectures/{id}/transcribe`, `GET /api/lectures/{id}/job` — queue a
  run and poll its progress (M1).
- `GET  /api/lectures/{id}/transcript` (JSON segments) and
  `/transcript.txt?timestamps=` (plain-text export) (M1).
- `POST /api/lectures/{id}/notes` (M2), `/slides` (M3), `/api/courses/{id}/chat`
  (M4), quiz/flashcard endpoints (M5)

## Quality bars

- Transcription accuracy is the foundation — prefer a bigger Whisper model over
  speed; a lecture may take a few minutes to transcribe and that's fine.
- Summaries must cite lecture structure (topics in order), not generic fluff.
- The tutor must answer from course material first and say when it's using
  outside knowledge or web results.
