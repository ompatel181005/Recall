"""Slide PDF ingestion.

Text is kept as one string with `[Slide N]` markers rather than a row per page,
so the summariser can cite a slide number and nothing about the database schema
has to change. Scanned, image-only decks yield no text — pypdf does not do OCR,
and that is out of scope, so those slides are marked rather than silently empty.
"""

from __future__ import annotations

import re
from pathlib import Path

# PDF text extraction produces ragged whitespace: trailing spaces from column
# layouts, and runs of blank lines between text boxes.
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")

NO_TEXT_MARKER = "(no extractable text — this slide is probably an image)"


def _tidy(text: str) -> str:
    return _BLANK_RUN.sub("\n\n", _TRAILING_SPACE.sub("", text)).strip()


def extract_pdf_text(pdf_path: str | Path) -> tuple[str, int]:
    """Return (text with [Slide N] markers, page count)."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))

    if reader.is_encrypted:
        # Many university decks are "protected" with an empty owner password,
        # which opens fine; a real password is the user's to remove.
        try:
            opened = reader.decrypt("")
        except Exception:
            opened = 0
        if not opened:
            raise ValueError("This PDF is password-protected — remove the password and re-upload")

    pages: list[str] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            body = _tidy(page.extract_text() or "")
        except Exception:
            body = ""  # one malformed page must not lose the rest of the deck
        pages.append(f"[Slide {number}]\n{body or NO_TEXT_MARKER}")

    return "\n\n".join(pages), len(reader.pages)


def page_count(extracted_text: str) -> int:
    """Slides in an already-extracted deck, without reopening the file."""
    return len(re.findall(r"^\[Slide \d+\]$", extracted_text, re.MULTILINE))


def has_text(extracted_text: str) -> bool:
    """False when every page came back empty — i.e. the deck needs OCR to be
    useful, so the UI can say so instead of implying the slides were read."""
    stripped = re.sub(r"^\[Slide \d+\]$", "", extracted_text, flags=re.MULTILINE)
    return bool(stripped.replace(NO_TEXT_MARKER, "").strip())
