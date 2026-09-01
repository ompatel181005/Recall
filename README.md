# Recall

**Record a lecture, get it back when you need it.**

Recall records your lectures, transcribes them locally on your own GPU, and
turns them into study notes and a tutor that answers from what your lecturer
actually said — citing the lecture and the minute it came from, so you can jump
straight to the audio and hear it yourself.

Everything runs on your machine. Transcription uses Whisper on the GPU, and the
AI tasks are routed per task in `config.yaml`, so you can stay entirely local
with Ollama or point any of them at Claude, Gemini or an OpenAI-compatible API.

- Record in the browser, or import an existing recording (mic, tab audio for
  online lectures, or both mixed)
- Timestamped transcripts with click-to-seek playback
- Structured study notes, with the lecturer's slide PDFs folded in
- A course tutor with citations back to the source lecture and timestamp

- Product spec: [docs/SPEC.md](docs/SPEC.md)
- Milestones: [docs/ROADMAP.md](docs/ROADMAP.md)

## Setup

Prereqs: Python 3.13+, Node 20+, Git, and **ffmpeg on PATH** (duration probing,
video→audio extraction, playback transcoding). Optional but recommended: an
NVIDIA GPU + driver (transcription falls back to CPU without one, much slower)
and [Ollama](https://ollama.com) running locally for free local LLM tasks
(`ollama pull qwen2.5:7b` and `ollama pull nomic-embed-text`). Ollama binds
IPv4 only, which is why the default URL is `127.0.0.1` and not `localhost` —
on Windows the latter tries IPv6 first and costs a timeout on every call.

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

## Access and security

**There is no authentication.** Anyone who can reach the ports can read every
recording, transcript and note. That is a deliberate trade for a single-user
local app, but it means where you bind matters:

- The backend binds `127.0.0.1` unless you pass `--host`, so it is not reachable
  from other machines on its own.
- The Vite dev server binds **all interfaces** (`host: true` in
  `vite.config.ts`) so you can open the app from your phone. Anyone on the same
  Wi-Fi can then reach it too, and it proxies straight through to the backend.

On your home network that is usually fine. On university or public Wi-Fi it
means classmates can browse your lectures. To keep it to this machine only, set
`host: false` in `vite.config.ts` or run `npm run dev -- --host 127.0.0.1`.

Recording lectures may also need your lecturer's or institution's permission —
that is on you, not the software.

## Configuration

`config.yaml` routes every AI task to a provider and model — switch any task
between local (Ollama) and cloud (Claude, Gemini, or any OpenAI-compatible
API) by editing that file. Transcription model/device also lives there. API
keys go in `.env` (see `.env.example`).

`tasks.summarize.compare_with` lists extra provider/model pairs the Notes tab
offers beside the default, so the same lecture can be summarised twice and
the results compared before you commit to a default.

Gemini is the cheapest good option: its free tier is generous, and unlike a
local 7B it does not invent textbook detail for topics the lecturer only
named. Get a key at <https://aistudio.google.com/apikey>, put it in `.env` as
`GEMINI_API_KEY`, then set `tasks.summarize.provider: gemini` to make it the
default.

## Notes

- Whisper models download from Hugging Face on first transcription (~1.5 GB for
  `distil-large-v3`), not at install time. The first run therefore looks slow.
- CUDA needs cuBLAS and cuDNN 9 at runtime. They install as the
  `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` dependencies, and
  `services/transcribe.py` puts their `site-packages` DLL folders on the search
  path at import — so no system PATH edits. If you ever see
  `Library cublas64_12.dll is not found`, those wheels are missing.
- Transcription runs one lecture at a time on a single background worker; extra
  lectures queue. Summarisation runs on its own worker alongside it.
  `/api/lectures/{id}/jobs` reports progress for both.
- The Tutor tab answers from a whole course at once. Lectures become
  searchable automatically once transcribed; the header says how many are
  indexed. Answers cite the lecture and timestamp they came from, and the
  citations are clickable.
- Changing `tasks.embeddings` invalidates every stored vector — vectors from
  different models are not comparable. Hit Re-index on each course after.
- Attaching the lecturer's slide PDF measurably improves notes: it fixes
  technical terms speech recognition mangles, and recovers material that was
  shown rather than said. Slide-sourced points are marked "(from slides)".
- Notes generated by a small local model should be checked against the
  transcript. A 7B model will sometimes supply the textbook definition of a
  topic the lecturer only mentioned in passing. Click any [MM:SS] in the notes
  to jump to what was actually said.
- All recordings, slides, and the database live under `data/` and are never
  committed. They persist across restarts; nothing deletes them on its own.
- Deleting a lecture or course moves its audio and text into `data/.trash/`,
  one timestamped folder per lecture with a `lecture.json` holding the title,
  transcript and notes. Nothing ever empties it — that is your call.
- Set `RECALL_DATA_DIR` to run against a throwaway data directory, which
  is what any automated test should do.
