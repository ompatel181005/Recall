"""Course-scoped question answering over indexed lectures and slides.

Sources are numbered before they reach the model and it is asked to cite by
number, rather than to write out lecture titles and timestamps itself. Numbers
are then mapped back to the real lecture and time on the way out, so a citation
can never point at a lecture that does not exist.
"""

from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from ..db import engine
from ..models import ChatMessage
from .index import course_stats, search
from .providers.registry import get_provider_for_task

TOP_K = 8

# Turns of prior conversation given to the model. Enough for "explain that
# again" to work, short enough not to crowd out the retrieved sources.
HISTORY_TURNS = 6

SYSTEM = """You are a tutor for one university course. You answer from that \
course's own lectures and slides.

You are given numbered sources retrieved from the student's recordings. Ground \
every claim in them and cite the source number in square brackets, like [2], \
immediately after the claim it supports. Cite several when several apply.

- If the sources do not cover the question, say so plainly and say what the \
course does cover nearby. Do not fill the gap from general knowledge.
- If you do add something from outside the course to make an explanation land, \
label it clearly as outside the course material, and keep it short.
- The sources are speech recognition output, so expect mangled technical terms; \
read through obvious errors rather than quoting them back.
- Teach, don't recite: explain in your own words, at the level of a student who \
attended the lecture but did not follow all of it.
- Be concise. No preamble."""

QUESTION_TEMPLATE = """Course: {course}

Sources:
{sources}

Question: {question}"""


def _format_sources(hits: list[dict]) -> str:
    blocks = []
    for number, hit in enumerate(hits, start=1):
        if hit["source"] == "slides":
            where = f"{hit['lecture_title']} — {hit['slide_label'] or 'slides'}"
        else:
            where = f"{hit['lecture_title']} — {_hhmm(hit['start_seconds'] or 0)}"
        blocks.append(f"[{number}] {where}\n{hit['text']}")
    return "\n\n".join(blocks)


def _hhmm(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _cited_numbers(answer: str) -> set[int]:
    """Which sources the model actually leaned on, so the UI can show those
    first and quietly keep the rest."""
    return {int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)}


def history_for(course_id: int, limit: int = HISTORY_TURNS) -> list[ChatMessage]:
    with Session(engine) as session:
        rows = session.exec(
            select(ChatMessage)
            .where(ChatMessage.course_id == course_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()
    return list(reversed(rows))


def ask(course_id: int, course_name: str, question: str) -> dict:
    """Answer one question and persist both turns. Returns the assistant turn."""
    previous = history_for(course_id)

    # A follow-up like "explain that again" embeds poorly on its own, so the
    # previous question rides along in the retrieval query only — never in the
    # question the model is asked to answer.
    last_user = next(
        (m.content for m in reversed(previous) if m.role == "user"), ""
    )
    retrieval_query = f"{last_user}\n{question}" if last_user and len(question) < 60 else question

    hits = search(course_id, retrieval_query, k=TOP_K)

    with Session(engine) as session:
        session.add(ChatMessage(course_id=course_id, role="user", content=question))
        session.commit()

    if not hits:
        stats = course_stats(course_id)
        answer = (
            "Nothing in this course is indexed yet, so I have nothing to answer from. "
            "Transcribe a lecture and it will be indexed automatically."
            if stats["chunks"] == 0
            else "I could not find anything relevant in this course's material."
        )
        return _store_answer(course_id, answer, [])

    messages = [
        {"role": m.role, "content": m.content}
        for m in previous
        if m.role in ("user", "assistant")
    ]
    messages.append(
        {
            "role": "user",
            "content": QUESTION_TEMPLATE.format(
                course=course_name, sources=_format_sources(hits), question=question
            ),
        }
    )

    provider = get_provider_for_task("chat")
    if not provider.available():
        raise RuntimeError(
            f"Chat provider '{provider.name}' is not available — check its API key "
            "in .env, or point tasks.chat at a running provider in config.yaml"
        )

    answer = provider.complete(messages, system=SYSTEM, max_tokens=1500, temperature=0.3).strip()

    cited = _cited_numbers(answer)
    citations = [
        {
            "n": number,
            "lecture_id": hit["lecture_id"],
            "lecture_title": hit["lecture_title"],
            "source": hit["source"],
            "start_seconds": hit["start_seconds"],
            "slide_label": hit["slide_label"],
            "snippet": hit["text"][:300],
            "score": hit["score"],
            "cited": number in cited,
        }
        for number, hit in enumerate(hits, start=1)
    ]
    return _store_answer(course_id, answer, citations)


def _store_answer(course_id: int, answer: str, citations: list[dict]) -> dict:
    with Session(engine) as session:
        row = ChatMessage(
            course_id=course_id,
            role="assistant",
            content=answer,
            citations_json=json.dumps(citations),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {
            "id": row.id,
            "course_id": course_id,
            "role": "assistant",
            "content": answer,
            "citations": citations,
            "created_at": row.created_at,
        }
