"""Lecture CRUD, audio upload, transcription control and transcript access."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import Lecture, LectureStatus, Note, SlideDeck, Transcript
from ..schemas import (
    LectureCreate,
    LectureRead,
    LectureUpdate,
    NoteRead,
    NotesRequest,
    TranscriptRead,
)
from ..services import jobs, media

router = APIRouter(prefix="/api/lectures", tags=["lectures"])

# Anything ffmpeg/Whisper can realistically open. Video is accepted because
# online lectures are often recorded as mp4/mkv — the audio gets extracted.
ALLOWED_SUFFIXES = {
    ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus", ".flac", ".wma",
    ".webm", ".mp4", ".mkv", ".mov", ".avi",
}


# Pinned rather than read from mimetypes, whose answers on Windows come from
# the registry and vary machine to machine — the browser needs the right one.
AUDIO_MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".opus": "audio/ogg", ".flac": "audio/flac", ".webm": "audio/webm",
}


def _audio_dir(lecture_id: int) -> Path:
    return settings.data_dir / "audio" / str(lecture_id)


def _read(session: Session, lecture: Lecture) -> LectureRead:
    has_transcript = (
        session.exec(select(Transcript.id).where(Transcript.lecture_id == lecture.id)).first()
        is not None
    )
    return LectureRead(
        **lecture.model_dump(),
        has_audio=bool(lecture.audio_path),
        has_transcript=has_transcript,
    )


def _get(session: Session, lecture_id: int) -> Lecture:
    lecture = session.get(Lecture, lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    return lecture


def _trash_lecture(lecture: Lecture, transcript: Transcript | None, notes: list[Note]) -> None:
    """Move a deleted lecture's audio aside instead of destroying it, with its
    text alongside so it can be restored by hand.

    A lecture is an irreplaceable recording of a one-off event: a mis-click on
    "Delete course" must not be able to lose a term's worth. Nothing reads
    data/.trash, so emptying it stays a deliberate, manual decision.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = settings.data_dir / ".trash" / f"{stamp}-lecture-{lecture.id}"
    destination.mkdir(parents=True, exist_ok=True)

    record = {
        "lecture": lecture.model_dump(mode="json"),
        "transcript": transcript.model_dump(mode="json") if transcript else None,
        "notes": [note.model_dump(mode="json") for note in notes],
    }
    (destination / "lecture.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    source = _audio_dir(lecture.id)
    if source.exists():
        try:
            shutil.move(str(source), str(destination / "audio"))
        except OSError:
            # Never let a filesystem problem block the delete the user asked for.
            shutil.rmtree(source, ignore_errors=True)


def delete_lecture_records(session: Session, lecture: Lecture) -> None:
    """Remove a lecture and everything hanging off it. Its audio and text are
    moved to data/.trash first. Caller commits. Shared with the course cascade."""
    transcript = session.exec(
        select(Transcript).where(Transcript.lecture_id == lecture.id)
    ).first()
    notes = list(session.exec(select(Note).where(Note.lecture_id == lecture.id)).all())
    _trash_lecture(lecture, transcript, notes)

    for model in (Transcript, Note, SlideDeck):
        for row in session.exec(select(model).where(model.lecture_id == lecture.id)).all():
            session.delete(row)
    session.delete(lecture)


@router.get("", response_model=list[LectureRead])
def list_lectures(
    course_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[LectureRead]:
    statement = select(Lecture)
    if course_id is not None:
        statement = statement.where(Lecture.course_id == course_id)
    lectures = session.exec(statement.order_by(Lecture.created_at.desc())).all()
    return [_read(session, lec) for lec in lectures]


@router.post("", response_model=LectureRead, status_code=201)
def create_lecture(payload: LectureCreate, session: Session = Depends(get_session)) -> LectureRead:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Lecture title is required")
    lecture = Lecture(
        course_id=payload.course_id, title=title, lecture_date=payload.lecture_date
    )
    session.add(lecture)
    session.commit()
    session.refresh(lecture)
    return _read(session, lecture)


@router.get("/{lecture_id}", response_model=LectureRead)
def get_lecture(lecture_id: int, session: Session = Depends(get_session)) -> LectureRead:
    return _read(session, _get(session, lecture_id))


@router.patch("/{lecture_id}", response_model=LectureRead)
def update_lecture(
    lecture_id: int, payload: LectureUpdate, session: Session = Depends(get_session)
) -> LectureRead:
    lecture = _get(session, lecture_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(lecture, field, value.strip() if isinstance(value, str) else value)
    session.add(lecture)
    session.commit()
    session.refresh(lecture)
    return _read(session, lecture)


@router.delete("/{lecture_id}", status_code=204)
def delete_lecture(lecture_id: int, session: Session = Depends(get_session)) -> None:
    delete_lecture_records(session, _get(session, lecture_id))
    session.commit()


@router.post("/{lecture_id}/audio", response_model=LectureRead)
async def upload_audio(
    lecture_id: int,
    file: UploadFile = File(...),
    transcribe: bool = Query(default=True, description="Queue transcription immediately"),
    session: Session = Depends(get_session),
) -> LectureRead:
    """Attach a recording (browser capture or an existing file) to a lecture."""
    lecture = _get(session, lecture_id)

    suffix = Path(file.filename or "").suffix.lower() or ".webm"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: "
            f"{', '.join(sorted(ALLOWED_SUFFIXES))}",
        )

    directory = _audio_dir(lecture_id)
    shutil.rmtree(directory, ignore_errors=True)   # replacing audio replaces the old file
    directory.mkdir(parents=True, exist_ok=True)

    source = directory / f"original{suffix}"
    with source.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    await file.close()

    if source.stat().st_size == 0:
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    # Browser WebM has no duration header, so give the player a seekable MP3.
    media.make_playback_copy(source, directory)

    lecture.audio_path = source.relative_to(settings.data_dir).as_posix()
    lecture.duration_seconds = media.probe_duration(source)
    lecture.status = LectureStatus.recorded
    session.add(lecture)
    session.commit()
    session.refresh(lecture)

    if transcribe:
        jobs.enqueue_transcription(lecture_id)
        session.refresh(lecture)

    return _read(session, lecture)


@router.api_route("/{lecture_id}/audio", methods=["GET", "HEAD"])
def get_audio(lecture_id: int, session: Session = Depends(get_session)) -> FileResponse:
    """Serves the recording. Starlette handles Range requests, so the player
    can seek."""
    lecture = _get(session, lecture_id)
    if not lecture.audio_path:
        raise HTTPException(status_code=404, detail="No audio attached to this lecture")

    playback = _audio_dir(lecture_id) / "playback.mp3"
    path = playback if playback.exists() else settings.data_dir / lecture.audio_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file is missing from disk")

    media_type = AUDIO_MIME.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/{lecture_id}/transcribe")
def start_transcription(lecture_id: int, session: Session = Depends(get_session)) -> dict:
    lecture = _get(session, lecture_id)
    if not lecture.audio_path:
        raise HTTPException(status_code=409, detail="Attach audio before transcribing")
    return jobs.enqueue_transcription(lecture_id)


@router.get("/{lecture_id}/jobs")
def lecture_jobs(lecture_id: int) -> dict:
    """Progress for this lecture's background work, one poll for every kind."""
    return {
        kind: jobs.get_job(kind, lecture_id) or {"status": "none"}
        for kind in jobs.LANE_FOR_KIND
    }


@router.post("/{lecture_id}/notes")
def generate_notes(
    lecture_id: int,
    payload: NotesRequest | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Queue study-note generation. With no body the provider comes from
    config.yaml; passing one runs a named provider instead, which is how the
    same lecture gets summarised twice for comparison."""
    _get(session, lecture_id)
    has_transcript = session.exec(
        select(Transcript.id).where(Transcript.lecture_id == lecture_id)
    ).first()
    if not has_transcript:
        raise HTTPException(
            status_code=409, detail="Transcribe this lecture before generating notes"
        )

    request = payload or NotesRequest()
    return jobs.enqueue_notes(lecture_id, provider=request.provider, model=request.model)


@router.get("/{lecture_id}/notes", response_model=list[NoteRead])
def list_notes(
    lecture_id: int, session: Session = Depends(get_session)
) -> list[Note]:
    return list(
        session.exec(
            select(Note)
            .where(Note.lecture_id == lecture_id)
            .order_by(Note.created_at.desc())
        ).all()
    )


@router.get("/{lecture_id}/transcript", response_model=TranscriptRead)
def get_transcript(lecture_id: int, session: Session = Depends(get_session)) -> TranscriptRead:
    transcript = session.exec(
        select(Transcript).where(Transcript.lecture_id == lecture_id)
    ).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="No transcript yet for this lecture")
    return TranscriptRead(
        lecture_id=lecture_id,
        full_text=transcript.full_text,
        segments=json.loads(transcript.segments_json or "[]"),
        language=transcript.language,
        model_used=transcript.model_used,
        created_at=transcript.created_at,
    )


@router.get("/{lecture_id}/transcript.txt", response_class=PlainTextResponse)
def export_transcript(
    lecture_id: int,
    timestamps: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    lecture = _get(session, lecture_id)
    transcript = session.exec(
        select(Transcript).where(Transcript.lecture_id == lecture_id)
    ).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="No transcript yet for this lecture")

    if timestamps:
        body = "\n".join(
            f"[{_hhmmss(seg['start'])}] {seg['text']}"
            for seg in json.loads(transcript.segments_json or "[]")
        )
    else:
        body = transcript.full_text

    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in lecture.title).strip()
    filename = f"{safe_title or 'transcript'}.txt"
    return PlainTextResponse(
        body, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def _hhmmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"
