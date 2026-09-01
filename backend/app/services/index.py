"""Chunking, embedding and retrieval for the course tutor.

Vectors live in the `chunk` table as raw float32 bytes and are searched by brute
force: load one course's vectors, one matrix multiply, take the top k. A
semester is a few thousand chunks, so that is sub-millisecond and needs no
vector index, no loadable SQLite extension and no extra service. Revisit around
100k chunks, where loading every vector per query starts to matter.

Vectors are L2-normalised on write, so cosine similarity is just a dot product.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
from sqlmodel import Session, delete, select

from ..db import engine
from ..models import Chunk, Lecture, SlideDeck, Transcript
from .providers.registry import get_embedder_for_task

# Retrieval works best on chunks big enough to carry an idea but small enough
# that a hit is specific. ~450 tokens is roughly three minutes of speech.
CHUNK_TARGET_TOKENS = 450
CHARS_PER_TOKEN = 4
CHUNK_TARGET_CHARS = CHUNK_TARGET_TOKENS * CHARS_PER_TOKEN

# One segment of overlap so a point made across a chunk boundary is still
# retrievable whole from at least one side.
OVERLAP_SEGMENTS = 1

EMBED_BATCH = 32

_SLIDE_MARKER = re.compile(r"^\[Slide (\d+)\]$", re.MULTILINE)


# --------------------------------------------------------------------------
# vectors


def to_blob(vector: list[float] | np.ndarray) -> bytes:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm > 0:
        array = array / norm
    return array.astype(np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


# --------------------------------------------------------------------------
# chunking


def chunk_transcript(segments: list[dict]) -> list[dict]:
    """Group timed segments into retrievable passages, keeping the time span so
    an answer can cite where in the audio it came from."""
    chunks: list[dict] = []
    current: list[dict] = []
    size = 0

    def flush() -> None:
        if not current:
            return
        chunks.append(
            {
                "text": " ".join(s["text"] for s in current).strip(),
                "start_seconds": current[0]["start"],
                "end_seconds": current[-1]["end"],
            }
        )

    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        if current and size + len(text) > CHUNK_TARGET_CHARS:
            flush()
            current = current[-OVERLAP_SEGMENTS:] if OVERLAP_SEGMENTS else []
            size = sum(len(s["text"]) for s in current)
        current.append({**segment, "text": text})
        size += len(text)

    flush()
    return chunks


def chunk_slides(extracted_text: str) -> list[dict]:
    """Split a deck on its `[Slide N]` markers, grouping consecutive slides up
    to the target size so one bullet does not become its own chunk."""
    parts = _SLIDE_MARKER.split(extracted_text)
    # split() gives [preamble, number, body, number, body, ...]
    slides = [
        (int(parts[i]), parts[i + 1].strip())
        for i in range(1, len(parts) - 1, 2)
        if parts[i + 1].strip()
    ]

    chunks: list[dict] = []
    current: list[tuple[int, str]] = []
    size = 0

    def flush() -> None:
        if not current:
            return
        first, last = current[0][0], current[-1][0]
        label = f"Slide {first}" if first == last else f"Slides {first}-{last}"
        body = "\n".join(f"[Slide {n}] {t}" for n, t in current)
        chunks.append({"text": body, "slide_label": label})

    for number, body in slides:
        if current and size + len(body) > CHUNK_TARGET_CHARS:
            flush()
            current, size = [], 0
        current.append((number, body))
        size += len(body)

    flush()
    return chunks


# --------------------------------------------------------------------------
# indexing


def _embed_all(texts: list[str], embedder, progress_cb=None) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        vectors.extend(embedder.embed(batch))
        if progress_cb:
            progress_cb(min((start + len(batch)) / len(texts), 0.99))
    return vectors


def reindex_lecture(
    lecture_id: int, progress_cb: Callable[[float, str], None] | None = None
) -> int:
    """Rebuild this lecture's chunks from its transcript and slides. Returns the
    number of chunks stored. Safe to re-run: existing chunks are replaced."""

    def report(fraction: float, message: str) -> None:
        if progress_cb:
            progress_cb(fraction, message)

    with Session(engine) as session:
        lecture = session.get(Lecture, lecture_id)
        if lecture is None:
            return 0
        course_id = lecture.course_id
        transcript = session.exec(
            select(Transcript).where(Transcript.lecture_id == lecture_id)
        ).first()
        decks = session.exec(
            select(SlideDeck).where(SlideDeck.lecture_id == lecture_id)
        ).all()
        deck_texts = [d.extracted_text for d in decks if d.extracted_text.strip()]

    pending: list[dict] = []
    if transcript and transcript.segments_json:
        import json

        for chunk in chunk_transcript(json.loads(transcript.segments_json)):
            pending.append({**chunk, "source": "transcript"})
    for deck_text in deck_texts:
        for chunk in chunk_slides(deck_text):
            pending.append({**chunk, "source": "slides"})

    if not pending:
        _replace_chunks(lecture_id, [])
        return 0

    report(0.05, f"Embedding {len(pending)} passages…")
    embedder = get_embedder_for_task("embeddings")
    if not embedder.available():
        raise RuntimeError(
            f"Embedding provider '{embedder.name}' is not available — "
            "start Ollama, or point tasks.embeddings elsewhere in config.yaml"
        )

    vectors = _embed_all(
        [c["text"] for c in pending],
        embedder,
        progress_cb=lambda f: report(0.05 + f * 0.9, f"Embedding… {int(f * 100)}%"),
    )

    rows = [
        Chunk(
            course_id=course_id,
            lecture_id=lecture_id,
            source=chunk["source"],
            ordinal=ordinal,
            start_seconds=chunk.get("start_seconds"),
            end_seconds=chunk.get("end_seconds"),
            slide_label=chunk.get("slide_label", ""),
            text=chunk["text"],
            embedding=to_blob(vector),
            model_used=f"{embedder.name}/{embedder.model}",
        )
        for ordinal, (chunk, vector) in enumerate(zip(pending, vectors))
    ]
    _replace_chunks(lecture_id, rows)
    return len(rows)


def _replace_chunks(lecture_id: int, rows: list[Chunk]) -> None:
    with Session(engine) as session:
        session.exec(delete(Chunk).where(Chunk.lecture_id == lecture_id))
        for row in rows:
            session.add(row)
        session.commit()


def run_job(job) -> None:
    """Job handler: (re)index one lecture."""
    from . import jobs

    count = reindex_lecture(
        job.lecture_id,
        progress_cb=lambda f, m: jobs.update(job, progress=f, message=m),
    )
    jobs.finish(job, f"Indexed {count} passage{'s' if count != 1 else ''}")


# --------------------------------------------------------------------------
# retrieval


def search(course_id: int, query: str, k: int = 8) -> list[dict]:
    """Top-k passages from a course, most similar first."""
    embedder = get_embedder_for_task("embeddings")
    if not embedder.available():
        raise RuntimeError(
            f"Embedding provider '{embedder.name}' is not available — "
            "start Ollama, or point tasks.embeddings elsewhere in config.yaml"
        )

    with Session(engine) as session:
        rows = session.exec(
            select(Chunk, Lecture.title)
            .join(Lecture, Lecture.id == Chunk.lecture_id)
            .where(Chunk.course_id == course_id)
        ).all()

    if not rows:
        return []

    matrix = np.vstack([from_blob(chunk.embedding) for chunk, _ in rows])
    question = np.asarray(embedder.embed([query])[0], dtype=np.float32)
    norm = float(np.linalg.norm(question))
    if norm > 0:
        question = question / norm

    if matrix.shape[1] != question.shape[0]:
        raise RuntimeError(
            "Stored vectors have a different width than the current embedding "
            "model — re-index the course after changing tasks.embeddings"
        )

    scores = matrix @ question
    best = np.argsort(-scores)[:k]

    results = []
    for position in best:
        chunk, lecture_title = rows[int(position)]
        results.append(
            {
                "chunk_id": chunk.id,
                "lecture_id": chunk.lecture_id,
                "lecture_title": lecture_title,
                "source": chunk.source,
                "start_seconds": chunk.start_seconds,
                "slide_label": chunk.slide_label,
                "text": chunk.text,
                "score": round(float(scores[int(position)]), 4),
            }
        )
    return results


def course_stats(course_id: int) -> dict:
    """How much of a course is searchable — the tutor says so up front rather
    than answering thinly from a half-indexed course."""
    with Session(engine) as session:
        chunks = session.exec(select(Chunk).where(Chunk.course_id == course_id)).all()
        lectures = session.exec(select(Lecture).where(Lecture.course_id == course_id)).all()
    indexed = {c.lecture_id for c in chunks}
    return {
        "chunks": len(chunks),
        "indexed_lectures": len(indexed),
        "total_lectures": len(lectures),
    }
