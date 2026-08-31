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
