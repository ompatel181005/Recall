"""Course tutor: ask questions across every indexed lecture in a course."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import ChatMessage, Course, Lecture
from ..schemas import ChatMessageRead, ChatRequest, IndexStatus
from ..services import index, jobs, tutor

router = APIRouter(prefix="/api/courses", tags=["chat"])


def _course(session: Session, course_id: int) -> Course:
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _read(row: ChatMessage) -> ChatMessageRead:
    return ChatMessageRead(
        id=row.id,
        course_id=row.course_id,
        role=row.role,
        content=row.content,
        citations=json.loads(row.citations_json or "[]"),
        created_at=row.created_at,
    )


@router.get("/{course_id}/chat", response_model=list[ChatMessageRead])
def get_history(
    course_id: int, session: Session = Depends(get_session)
) -> list[ChatMessageRead]:
    rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.course_id == course_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return [_read(row) for row in rows]


@router.post("/{course_id}/chat", response_model=ChatMessageRead)
def ask(
    course_id: int, payload: ChatRequest, session: Session = Depends(get_session)
) -> ChatMessageRead:
    """Answer a question from the course's own material.

    This one blocks rather than going through services/jobs.py. The rule there
    exists so batch work cannot monopolise the GPU while a request waits; a
    chat turn *is* the thing the user is waiting on, and FastAPI runs sync
    handlers in a threadpool, so blocking here does not stall the server.
    """
    course = _course(session, course_id)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Ask a question first")

    try:
        return ChatMessageRead(**tutor.ask(course_id, course.name, question))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/{course_id}/chat", status_code=204)
def clear_history(course_id: int, session: Session = Depends(get_session)) -> None:
    for row in session.exec(
        select(ChatMessage).where(ChatMessage.course_id == course_id)
    ).all():
        session.delete(row)
    session.commit()


@router.get("/{course_id}/index", response_model=IndexStatus)
def index_status(course_id: int, session: Session = Depends(get_session)) -> IndexStatus:
    _course(session, course_id)
    return IndexStatus(**index.course_stats(course_id))


@router.post("/{course_id}/index")
def reindex_course(course_id: int, session: Session = Depends(get_session)) -> dict:
    """Re-embed every lecture in the course — needed after changing
    tasks.embeddings, since vectors from different models are not comparable."""
    _course(session, course_id)
    lectures = session.exec(select(Lecture).where(Lecture.course_id == course_id)).all()
    for lecture in lectures:
        jobs.enqueue_index(lecture.id)
    return {"queued": len(lectures)}
