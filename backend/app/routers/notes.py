"""Reading, editing and deleting generated notes.

Generation itself is queued from the lectures router — a note belongs to a
lecture, but once it exists it's an object in its own right that the student
can edit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Note
from ..schemas import NoteRead, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _get(session: Session, note_id: int) -> Note:
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.get("/{note_id}", response_model=NoteRead)
def get_note(note_id: int, session: Session = Depends(get_session)) -> Note:
    return _get(session, note_id)


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: int, payload: NoteUpdate, session: Session = Depends(get_session)
) -> Note:
    """Notes are a study document — the student's edits win over the model's
    draft, so an edited note is never silently regenerated in place."""
    note = _get(session, note_id)
    note.content_md = payload.content_md
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get(session, note_id))
    session.commit()
