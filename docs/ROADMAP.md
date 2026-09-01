# Roadmap

Build simple first; each milestone is independently shippable and usable.

## M0 — Scaffold ✅ (done)

Repo, spec, config, runnable FastAPI skeleton with `/api/health`, provider
abstraction stubs, React shell that shows backend status.

## M1 — Record & Transcribe ✅ (done)

The app became genuinely useful: record a lecture, get a transcript.

- Course & Lecture CRUD (API + sidebar UI), cascading delete of audio files.
- Record in the browser (MediaRecorder) with pause/resume, elapsed clock and a
  live level meter; source picker for microphone (with input-device list),
  tab/screen audio for online lectures, or both mixed. Upload existing
  audio/video files instead; ffmpeg extracts audio and makes a seekable MP3.
- Background transcription job (faster-whisper on CUDA) behind a single worker
  thread; lecture status recorded → transcribing → ready/failed with live
  progress; first-run model download.
- Transcript viewer: timestamped segments, click-to-seek audio player with the
  current segment highlighted, in-transcript search, copy, and .txt export.

**Accept:** met — a lecture recording becomes a readable, timestamped
transcript without touching a terminal.

## M2 — Summaries & Notes ✅ (done)

- "Generate notes" on a ready lecture produces structured markdown (overview,
  topics in order, definitions, formulas, worked examples, exam hints, gaps)
  through the provider layer. Notes carry [MM:SS] timestamps that are clickable
  in the UI and seek the audio.
- Per-task routing proven: `tasks.summarize` picks the default and
  `tasks.summarize.compare_with` lists alternatives the UI offers, so the same
  lecture can be summarised by two models and compared. Each run is stored, so
  regenerating adds a run rather than overwriting one.
- Notes are editable and stored; the student's edit wins over the model draft.
- Long lectures (over ~12k tokens, roughly 80 minutes) are summarised section by
  section and merged, so nothing is silently truncated.

**Accept:** met — one click yields notes to revise from, and switching
`tasks.summarize.provider` in config.yaml changes the engine with no code edits.

**Known limitation:** qwen2.5:7b still occasionally supplies a standard textbook
definition for a topic the lecturer only named. Prompt work cut this down a lot
(see the worked example in `services/notes.py`) but did not eliminate it. Treat
local-model notes as a draft to check against the transcript; a frontier model
routed through `summarize` is the better choice when accuracy matters.

## M3 — Slides

- Upload one or more PDFs per lecture; extract text (pypdf; OCR fallback out of
  scope for now).
- Slide text included in the summarization prompt context; slides listed and
  viewable on the lecture page.

**Accept:** a lecture with slides produces notes that reference slide content.

## M4 — Q&A Tutor (RAG)

- Chunk transcripts + slide text; embed via `tasks.embeddings` (local
  nomic-embed-text by default); store vectors in sqlite-vec (fallback:
  ChromaDB).
- Course-scoped chat: retrieve top-k chunks across all lectures of a course,
  answer with citations (lecture title + timestamp).
- Chat UI with history per course.

**Accept:** "What did the professor say about X?" returns a correct answer
citing the right lecture and approximate time, for content 3+ lectures back.

## M5 — Quizzes, Flashcards & Web Search

- Generate quizzes (MCQ + short answer) and flashcards per lecture or per
  course; simple review UI, self-graded; export flashcards (CSV/Anki-friendly).
- Tutor gains web search: Claude's built-in web-search tool when routed to
  Claude; SearXNG/DuckDuckGo fallback for local mode. Answers label web-sourced
  material with links.

**Accept:** a course can be revised end-to-end in-app: read notes → drill
flashcards → take a quiz → ask the tutor, with web references when needed.

## Later / ideas backlog

- Live transcription during lecture (streaming Whisper).
- Slide-to-transcript time alignment.
- Speaker diarization (professor vs questions from students).
- Spaced-repetition scheduling for flashcards.
- Weekly digest across courses.
