"""Background job runner for slow work (GPU transcription, LLM calls).

Request handlers must never block on a model, so everything slow funnels
through here. Jobs are split into two lanes with one worker each:

  gpu — faster-whisper transcription. Serialised because the 8 GB card holds
        one Whisper model at a time.
  llm — summarisation and other provider calls. Kept separate so a note
        request doesn't sit behind a 40-minute transcription.

Note that a *local* LLM (Ollama) also uses the GPU, so routing `summarize` to
Ollama can contend with transcription for VRAM. Ollama manages its own memory
and will spill to CPU rather than fail, so this degrades rather than breaks.

Job state lives in memory; durable state (lecture status, transcripts, notes)
goes to SQLite, so a restart loses only progress percentages.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from ..db import engine
from ..models import Lecture, LectureStatus

LANE_FOR_KIND = {"transcribe": "gpu", "notes": "llm"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str                       # "<kind>:<lecture_id>" — one live job per pair
    kind: str
    lecture_id: int
    status: str = "queued"        # queued | running | done | failed
    progress: float = 0.0         # 0..1
    message: str = "Queued"
    error: str = ""
    result_id: int | None = None  # e.g. the Note row a notes job produced
    params: dict[str, Any] = field(default_factory=dict)
    queued_at: str = field(default_factory=_now)
    finished_at: str = ""


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
_queues: dict[str, queue.Queue[str]] = {}
_workers: dict[str, threading.Thread] = {}
_worker_lock = threading.Lock()

_handlers: dict[str, Callable[[Job], None]] = {}


def _handler_for(kind: str) -> Callable[[Job], None]:
    """Resolved on first use, not at import. The services below import this
    module back, so binding them at import time would deadlock on whichever
    module Python happened to load first."""
    if not _handlers:
        from . import notes as notes_service
        from . import transcribe as transcribe_service

        _handlers["transcribe"] = transcribe_service.run_job
        _handlers["notes"] = notes_service.run_job
    if kind not in _handlers:
        raise KeyError(f"No handler for job kind '{kind}'")
    return _handlers[kind]


def job_id(kind: str, lecture_id: int) -> str:
    return f"{kind}:{lecture_id}"


def get_job(kind: str, lecture_id: int) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id(kind, lecture_id))
        return asdict(job) if job else None


def all_jobs() -> list[dict]:
    with _jobs_lock:
        return [asdict(j) for j in _jobs.values()]


def queue_depth() -> int:
    return sum(q.qsize() for q in _queues.values())


def update(job: Job | str, **fields) -> None:
    key = job if isinstance(job, str) else job.id
    with _jobs_lock:
        target = _jobs.get(key)
        if target:
            for name, value in fields.items():
                setattr(target, name, value)


def enqueue(kind: str, lecture_id: int, **params) -> dict:
    """Queue a job. Re-queuing one already in flight is a no-op, so a
    double-click can't run the same work twice."""
    _handler_for(kind)  # fail fast on a bad kind, before anything is queued

    key = job_id(kind, lecture_id)
    with _jobs_lock:
        existing = _jobs.get(key)
        if existing and existing.status in ("queued", "running"):
            return asdict(existing)
        _jobs[key] = Job(id=key, kind=kind, lecture_id=lecture_id, params=params)

    if kind == "transcribe":
        _set_lecture_status(lecture_id, LectureStatus.transcribing)

    lane = LANE_FOR_KIND.get(kind, "llm")
    _ensure_worker(lane).put(key)
    return get_job(kind, lecture_id)  # type: ignore[return-value]


def _ensure_worker(lane: str) -> queue.Queue[str]:
    with _worker_lock:
        if lane not in _queues:
            _queues[lane] = queue.Queue()
        worker = _workers.get(lane)
        if worker is None or not worker.is_alive():
            worker = threading.Thread(
                target=_run_worker, args=(lane,), name=f"{lane}-worker", daemon=True
            )
            worker.start()
            _workers[lane] = worker
        return _queues[lane]


def _run_worker(lane: str) -> None:
    work = _queues[lane]
    while True:
        key = work.get()
        try:
            with _jobs_lock:
                job = _jobs.get(key)
            if job is None:
                continue
            update(key, status="running", message="Starting…")
            _handler_for(job.kind)(job)
        except Exception as exc:  # one bad job must not kill the lane
            fail(key, f"{type(exc).__name__}: {exc}")
        finally:
            work.task_done()


def finish(job: Job | str, message: str, result_id: int | None = None) -> None:
    update(job, status="done", progress=1.0, message=message,
           result_id=result_id, finished_at=_now())


def fail(job: Job | str, error: str) -> None:
    key = job if isinstance(job, str) else job.id
    update(key, status="failed", error=error, message="Failed", finished_at=_now())
    with _jobs_lock:
        target = _jobs.get(key)
    if target and target.kind == "transcribe":
        _set_lecture_status(target.lecture_id, LectureStatus.failed)


def _set_lecture_status(lecture_id: int, status: LectureStatus) -> None:
    with Session(engine) as session:
        lecture = session.get(Lecture, lecture_id)
        if lecture:
            lecture.status = status
            session.add(lecture)
            session.commit()


def enqueue_transcription(lecture_id: int) -> dict:
    return enqueue("transcribe", lecture_id)


def enqueue_notes(lecture_id: int, provider: str = "", model: str = "") -> dict:
    return enqueue("notes", lecture_id, provider=provider, model=model)
