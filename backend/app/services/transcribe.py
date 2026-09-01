"""faster-whisper transcription, running locally on the GPU.

The model is expensive to load (seconds, plus a one-off download on first use)
so it is loaded lazily and kept alive for the process. Only one transcription
runs at a time — see services/jobs.py, which owns the single worker thread that
calls in here.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..config import settings


def _register_cuda_dlls() -> None:
    """CTranslate2 loads cuBLAS/cuDNN at runtime. They ship as pip wheels
    (nvidia-cublas-cu12, nvidia-cudnn-cu12) that drop their DLLs inside
    site-packages, where Windows won't look — so put those directories on the
    search path here rather than making the user edit their system PATH.
    Without this, CUDA transcription dies with "cublas64_12.dll is not found"."""
    if os.name != "nt":
        return
    try:
        import nvidia
    except ImportError:
        return

    bin_dirs = [str(d) for base in nvidia.__path__ for d in Path(base).glob("*/bin")]
    if not bin_dirs:
        return
    for bin_dir in bin_dirs:
        with suppress(OSError):
            os.add_dll_directory(bin_dir)
    # add_dll_directory alone isn't enough: CTranslate2 resolves these through
    # the plain Win32 search order, which consults PATH.
    os.environ["PATH"] = os.pathsep.join([*bin_dirs, os.environ.get("PATH", "")])


_register_cuda_dlls()

_model: Any = None
_model_key: tuple[str, str, str] | None = None
_model_lock = threading.Lock()


def cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _resolve_device() -> tuple[str, str]:
    """(device, compute_type) from config.yaml, falling back to CPU if the GPU
    isn't usable so a missing driver degrades instead of erroring out."""
    device = settings.transcription.get("device", "auto")
    compute_type = settings.transcription.get("compute_type", "int8_float16")

    if device == "auto":
        device = "cuda" if cuda_available() else "cpu"
    elif device == "cuda" and not cuda_available():
        device = "cpu"

    if device == "cpu":
        compute_type = "int8"
    return device, compute_type


def model_is_loaded() -> bool:
    return _model is not None


def get_model() -> Any:
    """Load (and cache) the WhisperModel named in config.yaml."""
    global _model, _model_key

    name = settings.transcription.get("model", "distil-large-v3")
    device, compute_type = _resolve_device()
    key = (name, device, compute_type)

    with _model_lock:
        if _model is None or _model_key != key:
            from faster_whisper import WhisperModel

            _model = WhisperModel(name, device=device, compute_type=compute_type)
            _model_key = key
        return _model


def transcribe_audio(
    audio_path: str | Path,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict:
    """Transcribe one file. `progress_cb(fraction, message)` is called as
    segments stream in. Returns {full_text, segments, language, duration,
    model_used}."""
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    if progress_cb and not model_is_loaded():
        progress_cb(0.0, "Loading Whisper model (first run downloads it)…")

    model = get_model()
    name = settings.transcription.get("model", "distil-large-v3")
    device, _ = _resolve_device()

    if progress_cb:
        progress_cb(0.0, "Transcribing…")

    # Distil models are English-only; the full models auto-detect.
    language = "en" if name.startswith("distil") else None

    segment_iter, info = model.transcribe(
        str(path),
        beam_size=5,
        language=language,
        vad_filter=True,                 # skip silence between slides/questions
        condition_on_previous_text=False,  # avoids repetition loops on long lectures
    )

    total = info.duration or 0.0
    segments: list[dict] = []
    texts: list[str] = []

    for seg in segment_iter:
        segments.append(
            {"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()}
        )
        texts.append(seg.text.strip())
        if progress_cb and total:
            progress_cb(min(seg.end / total, 0.99), f"Transcribing… {len(segments)} segments")

    return {
        "full_text": " ".join(texts).strip(),
        "segments": segments,
        "language": info.language or (language or ""),
        "duration": total,
        "model_used": f"{name} ({device})",
    }


def run_job(job) -> None:
    """Job handler: transcribe a lecture's audio and store the transcript."""
    import json

    from sqlmodel import Session, select

    from ..db import engine
    from ..models import Lecture, LectureStatus, Transcript
    from . import jobs

    with Session(engine) as session:
        lecture = session.get(Lecture, job.lecture_id)
        if lecture is None:
            jobs.fail(job, "Lecture no longer exists")
            return
        source = settings.data_dir / lecture.audio_path if lecture.audio_path else None

    if source is None or not source.exists():
        jobs.fail(job, "No audio file attached to this lecture")
        return

    def on_progress(fraction: float, message: str) -> None:
        jobs.update(job, progress=fraction, message=message)

    result = transcribe_audio(source, progress_cb=on_progress)

    with Session(engine) as session:
        existing = session.exec(
            select(Transcript).where(Transcript.lecture_id == job.lecture_id)
        ).first()
        transcript = existing or Transcript(lecture_id=job.lecture_id)
        transcript.full_text = result["full_text"]
        transcript.segments_json = json.dumps(result["segments"])
        transcript.language = result["language"]
        transcript.model_used = result["model_used"]
        session.add(transcript)

        lecture = session.get(Lecture, job.lecture_id)
        if lecture:
            lecture.status = LectureStatus.ready
            if not lecture.duration_seconds and result.get("duration"):
                lecture.duration_seconds = result["duration"]
            session.add(lecture)
        session.commit()

    jobs.finish(job, f"Done — {len(result['segments'])} segments")
