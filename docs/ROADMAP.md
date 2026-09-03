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

## M3 — Slides ✅ (done)

- Upload one or more decks per lecture — PDF, PPTX, or legacy PPT. PowerPoint
  is read natively (python-pptx), which keeps tables and speaker notes that a
  PDF export drops; only legacy .ppt is converted first. Text is extracted at
  upload time
  so a broken or image-only deck is reported while the user is still looking at
  it; a deck with no readable text is flagged "no text" rather than silently
  contributing nothing. OCR remains out of scope.
- Slide text is passed to the summariser alongside the transcript, capped so a
  huge deck cannot crowd out the lecture. Notes mark slide-sourced points
  "(from slides)", which also tells the student which parts they will not hear
  in the recording.
- Decks are listed on the lecture's Slides tab, with the PDF viewable inline and
  the extracted text inspectable — worth checking when a deck yields odd notes.

**Accept:** met — with the deck attached, notes picked up the Dirichlet
conditions, the square-wave coefficients and the Gibbs overshoot figure, none of
which are anywhere in the audio.

## M4 — Q&A Tutor (RAG) ✅ (done)

- Transcripts and slide text are chunked (~450 tokens, one segment of overlap)
  and embedded via `tasks.embeddings` — local `nomic-embed-text` by default.
  Indexing happens automatically when a transcription finishes or slides change,
  so nothing has to be asked for.
- Vectors live in the `chunk` table as float32 bytes, searched by brute force in
  numpy. A semester is a few thousand chunks, so a dot product beats adding a
  vector index, a loadable SQLite extension or a second service. Revisit around
  100k chunks.
- Course-scoped chat retrieves the top 8 passages across every lecture and
  answers from them. Sources are numbered before the model sees them and it
  cites by number, so a citation can never point at a lecture that does not
  exist. Citations render as chips that open the lecture at that timestamp.
- Chat history is stored per course, and the last turns are given back to the
  model so follow-ups work.

**Accept:** met — asking about aliasing, the Laplace transform and impulse
response each cited the correct lecture out of four, and a question about
material the course never covered was refused rather than answered.

**Known limitation:** retrieval is pure vector similarity. A question phrased in
words the lecturer never used may miss; hybrid keyword + vector search is the
fix if that shows up in practice.

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
