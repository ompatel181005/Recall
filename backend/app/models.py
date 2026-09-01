"""Domain schema: Course -> Lecture -> Transcript / SlideDeck / Note.

See docs/SPEC.md for the domain model. Files (audio, PDFs) live on disk under
data/ and are referenced here by relative path, never stored as blobs.
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


class Chunk(SQLModel, table=True):
    """A retrievable slice of a lecture, with its embedding.

    Vectors are stored as raw float32 bytes and searched by brute force in
    numpy (see services/index.py). A semester is a few thousand chunks — a
    dot product over that is sub-millisecond, so a vector index would add a
    dependency and buy nothing until roughly 100k chunks.
    """

    id: int | None = Field(default=None, primary_key=True)
    # Denormalised from lecture so course-scoped retrieval is a single query.
    course_id: int = Field(foreign_key="course.id", index=True)
    lecture_id: int = Field(foreign_key="lecture.id", index=True)
    source: str = "transcript"    # transcript | slides
    ordinal: int = 0              # position within the lecture, for stable ordering
    start_seconds: float | None = None   # transcript chunks: where to seek back to
    end_seconds: float | None = None
    slide_label: str = ""         # slides chunks: e.g. "Slides 3-5"
    text: str = ""
    embedding: bytes = b""        # float32, L2-normalised at write time
    model_used: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class ChatMessage(SQLModel, table=True):
    """One turn of the course tutor conversation."""

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    role: str = "user"            # user | assistant
    content: str = ""
    citations_json: str = "[]"    # assistant turns: the sources behind the answer
    created_at: datetime = Field(default_factory=_utcnow)
