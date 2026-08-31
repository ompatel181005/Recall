"""Background job runner for GPU work.

Request handlers must never block on transcription, and the 8 GB GPU can only
hold one Whisper model anyway — so everything funnels through a single daemon
worker thread that processes one lecture at a time. Job state lives in memory;
durable state (lecture status, the transcript itself) goes to SQLite, so a
restart loses only progress percentages.
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..db import engine
from ..models import Lecture, LectureStatus, Transcript
from .transcribe import transcribe_audio


@dataclass
class Job:
    lecture_id: int
    status: str = "queued"        # queued | running | done | failed
    progress: float = 0.0         # 0..1
    message: str = "Queued"
    error: str = ""
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""


_jobs: dict[int, Job] = {}
_jobs_lock = threading.Lock()
_queue: queue.Queue[int] = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def get_job(lecture_id: int) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(lecture_id)
        return asdict(job) if job else None


def all_jobs() -> list[dict]:
    with _jobs_lock:
        return [asdict(j) for j in _jobs.values()]


def queue_depth() -> int:
    return _queue.qsize()


def _update(lecture_id: int, **fields) -> None:
    with _jobs_lock:
        job = _jobs.get(lecture_id)
        if job:
            for key, value in fields.items():
                setattr(job, key, value)


def enqueue_transcription(lecture_id: int) -> dict:
    """Queue a lecture for transcription. Re-queuing one already in flight is a
    no-op so a double-click can't run the GPU twice on the same file."""
    with _jobs_lock:
        existing = _jobs.get(lecture_id)
        if existing and existing.status in ("queued", "running"):
            return asdict(existing)
        _jobs[lecture_id] = Job(lecture_id=lecture_id)

    with Session(engine) as session:
        lecture = session.get(Lecture, lecture_id)
        if lecture:
            lecture.status = LectureStatus.transcribing
            session.add(lecture)
            session.commit()

    _ensure_worker()
    _queue.put(lecture_id)
    return get_job(lecture_id)  # type: ignore[return-value]


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run_worker, name="transcribe-worker", daemon=True)
            _worker.start()


def _run_worker() -> None:
    while True:
        lecture_id = _queue.get()
        try:
            _process(lecture_id)
        except Exception as exc:  # a bad file must not kill the worker
            _fail(lecture_id, f"{type(exc).__name__}: {exc}")
        finally:
            _queue.task_done()


def _process(lecture_id: int) -> None:
    from ..config import settings

    with Session(engine) as session:
        lecture = session.get(Lecture, lecture_id)
        if lecture is None:
            _fail(lecture_id, "Lecture no longer exists")
            return
        source = settings.data_dir / lecture.audio_path if lecture.audio_path else None

    if source is None or not source.exists():
        _fail(lecture_id, "No audio file attached to this lecture")
        return

    _update(lecture_id, status="running", message="Starting…")

    def on_progress(fraction: float, message: str) -> None:
        _update(lecture_id, progress=fraction, message=message)

    result = transcribe_audio(source, progress_cb=on_progress)

    with Session(engine) as session:
        existing = session.exec(
            select(Transcript).where(Transcript.lecture_id == lecture_id)
        ).first()
        transcript = existing or Transcript(lecture_id=lecture_id)
        transcript.full_text = result["full_text"]
        transcript.segments_json = json.dumps(result["segments"])
        transcript.language = result["language"]
        transcript.model_used = result["model_used"]
        session.add(transcript)

        lecture = session.get(Lecture, lecture_id)
        if lecture:
            lecture.status = LectureStatus.ready
            if not lecture.duration_seconds and result.get("duration"):
                lecture.duration_seconds = result["duration"]
            session.add(lecture)
        session.commit()

    _update(
        lecture_id,
        status="done",
        progress=1.0,
        message=f"Done — {len(result['segments'])} segments",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


def _fail(lecture_id: int, error: str) -> None:
    _update(
        lecture_id,
        status="failed",
        error=error,
        message="Failed",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    with Session(engine) as session:
        lecture = session.get(Lecture, lecture_id)
        if lecture:
            lecture.status = LectureStatus.failed
            session.add(lecture)
            session.commit()
