"""Request/response shapes for the API. Kept separate from models.py so the
wire format can differ from the table layout (segments as JSON, computed flags)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from .models import LectureStatus


class CourseCreate(BaseModel):
    name: str
    code: str = ""
    term: str = ""


class CourseUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    term: str | None = None


class CourseRead(BaseModel):
    id: int
    name: str
    code: str
    term: str
    created_at: datetime
    lecture_count: int = 0


class LectureCreate(BaseModel):
    course_id: int
    title: str
    lecture_date: date | None = None


class LectureUpdate(BaseModel):
    title: str | None = None
    lecture_date: date | None = None


class LectureRead(BaseModel):
    id: int
    course_id: int
    title: str
    lecture_date: date | None
    status: LectureStatus
    duration_seconds: float | None
    created_at: datetime
    has_audio: bool = False
    has_transcript: bool = False


class Segment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptRead(BaseModel):
    lecture_id: int
    full_text: str
    segments: list[Segment]
    language: str
    model_used: str
    created_at: datetime


class NoteRead(BaseModel):
    id: int
    lecture_id: int
    kind: str
    content_md: str
    provider_used: str
    created_at: datetime


class NoteUpdate(BaseModel):
    content_md: str


class NotesRequest(BaseModel):
    """Optional override so the same lecture can be summarised by a second
    provider and the two compared. Empty means "use config.yaml"."""

    provider: str = ""
    model: str = ""


class ProviderOption(BaseModel):
    provider: str
    model: str
    is_default: bool
    available: bool


class SlideDeckRead(BaseModel):
    """Deck metadata. The extracted text can run to tens of thousands of
    characters, so it is fetched separately rather than in every list."""

    id: int
    lecture_id: int
    filename: str
    page_count: int
    has_text: bool
    created_at: datetime
