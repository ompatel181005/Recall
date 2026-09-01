"""Course CRUD. Routers stay thin: validation, DB reads, delegation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import ChatMessage, Course, Lecture
from ..schemas import CourseCreate, CourseRead, CourseUpdate
from .lectures import delete_lecture_records

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _read(course: Course, lecture_count: int = 0) -> CourseRead:
    return CourseRead(**course.model_dump(), lecture_count=lecture_count)


@router.get("", response_model=list[CourseRead])
def list_courses(session: Session = Depends(get_session)) -> list[CourseRead]:
    courses = session.exec(select(Course).order_by(Course.created_at.desc())).all()
    counts = dict(
        session.exec(
            select(Lecture.course_id, func.count(Lecture.id)).group_by(Lecture.course_id)
        ).all()
    )
    return [_read(c, counts.get(c.id, 0)) for c in courses]


@router.post("", response_model=CourseRead, status_code=201)
def create_course(payload: CourseCreate, session: Session = Depends(get_session)) -> CourseRead:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Course name is required")
    course = Course(name=name, code=payload.code.strip(), term=payload.term.strip())
    session.add(course)
    session.commit()
    session.refresh(course)
    return _read(course)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: int, session: Session = Depends(get_session)) -> CourseRead:
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    count = session.exec(
        select(func.count(Lecture.id)).where(Lecture.course_id == course_id)
    ).one()
    return _read(course, count)


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: int, payload: CourseUpdate, session: Session = Depends(get_session)
) -> CourseRead:
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(course, field, value.strip() if isinstance(value, str) else value)
    session.add(course)
    session.commit()
    session.refresh(course)
    return _read(course)


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: int, session: Session = Depends(get_session)) -> None:
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    lectures = session.exec(select(Lecture).where(Lecture.course_id == course_id)).all()
    for lecture in lectures:
        delete_lecture_records(session, lecture)
    for message in session.exec(
        select(ChatMessage).where(ChatMessage.course_id == course_id)
    ).all():
        session.delete(message)
    session.delete(course)
    session.commit()
