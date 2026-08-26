# Roadmap

Build simple first; each milestone is independently shippable and usable.

## M0 — Scaffold ✅ (done)

Repo, spec, config, runnable FastAPI skeleton with `/api/health`, provider
abstraction stubs, React shell that shows backend status.

## M1 — Record & Transcribe

The app becomes genuinely useful: record a lecture, get a transcript.

- Course & Lecture CRUD (API + sidebar UI).
- Record in the browser (MediaRecorder) with pause/resume; input-device picker
  (covers mic and system-loopback for online lectures). Upload existing
  audio/video files; ffmpeg audio extraction.
- Background transcription job (faster-whisper on CUDA), lecture status
  recorded → transcribing → ready; first-run model download.
- Transcript viewer: timestamped segments, click-to-seek audio player, plain-text
  export.

**Accept:** record 5 min of speech in class conditions → readable, timestamped
transcript appears without touching a terminal.

## M2 — Summaries & Notes

- "Generate notes" on a ready lecture → structured markdown (topics in order,
  key concepts, definitions, open questions) via the provider layer.
- Per-task routing proven: same lecture summarized via Ollama and via Claude,
  compared side by side; pick defaults in config.yaml.
- Notes editable and stored; regenerate on demand.

**Accept:** one click on a transcribed lecture yields notes good enough to
revise from; switching `tasks.summarize.provider` in config.yaml changes the
engine with no code edits.

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
