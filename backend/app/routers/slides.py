"""Serving and removing individual slide decks.

Uploading and listing live on the lectures router — a deck is attached to a
lecture — but once it exists it is addressed on its own, like a note.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import SlideDeck
from ..services import jobs

router = APIRouter(prefix="/api/slides", tags=["slides"])


def _get(session: Session, deck_id: int) -> SlideDeck:
    deck = session.get(SlideDeck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Slide deck not found")
    return deck


@router.get("/{deck_id}/file")
def get_pdf(deck_id: int, session: Session = Depends(get_session)) -> FileResponse:
    """The PDF itself, shown inline so the browser's own viewer opens it."""
    deck = _get(session, deck_id)
    path = settings.data_dir / deck.pdf_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF is missing from disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{Path(deck.filename).name}"'},
    )


@router.get("/{deck_id}/text", response_class=PlainTextResponse)
def get_text(deck_id: int, session: Session = Depends(get_session)) -> str:
    """What the summariser actually sees — worth being able to check when a
    deck produces surprising notes."""
    return _get(session, deck_id).extracted_text


@router.delete("/{deck_id}", status_code=204)
def delete_deck(deck_id: int, session: Session = Depends(get_session)) -> None:
    """The PDF is deleted outright, unlike a recording: the student still has
    the original file it came from, so it is not irreplaceable."""
    deck = _get(session, deck_id)
    lecture_id = deck.lecture_id
    (settings.data_dir / deck.pdf_path).unlink(missing_ok=True)
    session.delete(deck)
    session.commit()
    jobs.enqueue_index(lecture_id)  # drop this deck's passages from the index
