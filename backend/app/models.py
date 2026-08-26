"""Domain schema: Course -> Lecture -> Transcript / SlideDeck / Note.

Schema only for M0; CRUD arrives in M1. See docs/SPEC.md for the domain model.
"""

from datetime import date, datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LectureStatus(str, Enum):
    recorded = "recorded"
    transcribing = "transcribing"
    ready = "ready"
    failed = "failed"


class Course(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    code: str = ""
    term: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Lecture(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    title: str
    lecture_date: date | None = None
    status: LectureStatus = LectureStatus.recorded
    audio_path: str = ""          # relative to data/
    duration_seconds: float | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Transcript(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lecture_id: int = Field(foreign_key="lecture.id", index=True, unique=True)
    full_text: str = ""
    segments_json: str = "[]"     # [{start, end, text}]
    language: str = ""
    model_used: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class SlideDeck(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lecture_id: int = Field(foreign_key="lecture.id", index=True)
    filename: str
    pdf_path: str                 # relative to data/
    extracted_text: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lecture_id: int = Field(foreign_key="lecture.id", index=True)
    kind: str = "summary"         # summary | custom (quiz/flashcards get own tables in M5)
    content_md: str = ""
    provider_used: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
