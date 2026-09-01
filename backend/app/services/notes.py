"""Turns a transcript into structured study notes through the provider layer.

Which model does the work is config, not code: `tasks.summarize` in config.yaml
picks the default, and `tasks.summarize.compare_with` lists alternatives the UI
offers, so the same lecture can be summarised locally and in the cloud and the
results compared before committing to a default.

A note on the prompt: small local models will happily fill a named-but-not-taught
topic with the standard textbook treatment. Negative rules alone did not stop
qwen2.5:7b doing this; the worked example near the end of NOTES_TEMPLATE did.
Keep it if you edit the prompt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from sqlmodel import Session, select

from ..db import engine
from ..models import Course, Lecture, Note, Transcript
from .providers.base import LLMProvider
from .providers.registry import get_provider, get_provider_for_task

# Roughly 4 characters per token for English prose. Only used to decide whether
# a transcript needs splitting, so an estimate is good enough.
CHARS_PER_TOKEN = 4

# Below this, the whole lecture goes to the model in one pass, which produces
# far more coherent notes. Above it, we summarise section by section and merge.
# 12k tokens is about 80 minutes of speech and fits every model we route to.
SINGLE_PASS_TOKEN_BUDGET = 12_000
SECTION_TOKEN_BUDGET = 7_000

SYSTEM = """You write study notes for a university student from a lecture transcript.

The transcript comes from automatic speech recognition: it contains mis-heard \
technical terms, unreliable punctuation and no speaker labels. Infer the intended \
term when the context makes it obvious; when a passage is too garbled to \
interpret, say so rather than guessing at it.

Rules:
- Follow the lecture's own order. Do not reorganise the material into a textbook \
structure.
- Write only what this transcript supports. Never add outside facts, definitions, \
formulas or examples the lecturer did not actually give.
- If the lecturer only announces or names a topic without developing it, record \
that it was introduced but not covered, and move on. Do NOT supply the standard \
textbook treatment in its place. A gap the student can see is far more useful \
than invented detail they revise from and trust.
- Never write down a formula, derivation or result the lecturer did not state.
- Cite approximate timestamps as [MM:SS] on each topic heading and on anything \
worth returning to, so the student can jump back to the audio.
- Prefer the lecturer's own phrasing for definitions.
- Omit any section heading you have no real content for. Never emit an empty \
heading.
- Be concise: bullets over paragraphs, no preamble, no "in this lecture" filler."""

NOTES_TEMPLATE = """Course: {course}
Lecture: {title}

Write study notes as GitHub-flavoured markdown using the sections below. Drop \
any section this lecture genuinely does not contain — an omitted section is \
correct, an invented one is not.

## Overview
Two or three sentences on what this lecture covered.

## Topics
### <topic name> [MM:SS]
- the substance of that topic, in the order presented

## Key concepts and definitions
- **term** — the definition as the lecturer gave it

## Formulas and results

## Worked examples

## Exam and assessment hints
Anything the lecturer flagged as important, examinable, or a common mistake.

## Open questions and gaps
Points left unexplained, contradictions, or places the audio was unusable.

Worked example of the discipline required, because this is the most common way
these notes go wrong:

  Transcript says: "[03:10] Next we'll derive the coefficients, then look at a
                    square wave."
  Correct notes:   "### Deriving the coefficients [03:10]
                    - Introduced here, but the derivation itself is not in this
                      recording."
  Wrong notes:     writing out the coefficient integrals. The lecturer never
                   said them, so they must not appear, however standard they are.

Transcript:
{transcript}"""

SECTION_TEMPLATE = """This is part {index} of {total} of a longer lecture transcript.

Write detailed bullet notes for this part only, keeping [MM:SS] timestamps on \
each point. Do not write an overview, introduction or conclusion — the parts \
will be merged afterwards. Write only what this part of the transcript says.

Transcript part:
{transcript}"""

MERGE_TEMPLATE = """Below are section notes taken from consecutive parts of one \
lecture, in order.

Course: {course}
Lecture: {title}

Merge them into a single set of study notes as GitHub-flavoured markdown, using \
the sections below. Keep the [MM:SS] timestamps. Remove repetition across \
sections, but do not drop material, and never add material that is not in the \
section notes. Omit any section the lecture does not contain.

## Overview
## Topics (### per topic, with [MM:SS])
## Key concepts and definitions
## Formulas and results
## Worked examples
## Exam and assessment hints
## Open questions and gaps

Section notes:
{sections}"""

_HEADING = re.compile(r"^(#{2,6})\s")


def strip_empty_sections(markdown: str) -> str:
    """Drop headings the model emitted with nothing under them.

    Models reliably echo the requested section list even when told to omit the
    unused ones, so this is enforced here rather than asked for again — a
    deterministic pass beats another prohibition in the prompt. A heading
    survives if it has text of its own or a surviving subheading.
    """
    lines = markdown.split("\n")
    headings = [
        (i, len(m.group(1))) for i, line in enumerate(lines) if (m := _HEADING.match(line))
    ]
    if not headings:
        return markdown.strip()

    bounds = [h[0] for h in headings] + [len(lines)]
    keep = [
        any(line.strip() for line in lines[bounds[k] + 1 : bounds[k + 1]])
        for k in range(len(headings))
    ]

    # A parent with no text of its own survives if any child survived, so walk
    # backwards and let that decision propagate upwards.
    for k in range(len(headings) - 1, -1, -1):
        if keep[k]:
            continue
        level = headings[k][1]
        j = k + 1
        while j < len(headings) and headings[j][1] > level:
            if keep[j]:
                keep[k] = True
                break
            j += 1

    dropped = {
        index
        for k in range(len(headings))
        if not keep[k]
        for index in range(bounds[k], bounds[k + 1])
    }
    result = "\n".join(line for i, line in enumerate(lines) if i not in dropped)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _hhmm(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def transcript_lines(segments: list[dict]) -> str:
    """`[MM:SS] text` per segment — the timestamps are what let the notes point
    back into the audio."""
    return "\n".join(f"[{_hhmm(s['start'])}] {s['text']}" for s in segments)


def _chunk(segments: list[dict], budget: int) -> list[list[dict]]:
    """Split on segment boundaries so no sentence is cut in half."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for segment in segments:
        cost = estimate_tokens(segment["text"]) + 6  # + the timestamp prefix
        if current and size + cost > budget:
            chunks.append(current)
            current, size = [], 0
        current.append(segment)
        size += cost
    if current:
        chunks.append(current)
    return chunks


def generate_markdown(
    provider: LLMProvider,
    course_name: str,
    lecture_title: str,
    segments: list[dict],
    progress_cb: Callable[[float, str], None] | None = None,
) -> str:
    """One pass for a normal lecture; section-then-merge for a long one."""
    body = transcript_lines(segments)

    def report(fraction: float, message: str) -> None:
        if progress_cb:
            progress_cb(fraction, message)

    if estimate_tokens(body) <= SINGLE_PASS_TOKEN_BUDGET:
        report(0.2, f"Summarising with {provider.name}/{provider.model}…")
        return strip_empty_sections(
            provider.complete(
                [{
                    "role": "user",
                    "content": NOTES_TEMPLATE.format(
                        course=course_name, title=lecture_title, transcript=body
                    ),
                }],
                system=SYSTEM,
                max_tokens=4096,
                temperature=0.3,
            )
        )

    chunks = _chunk(segments, SECTION_TOKEN_BUDGET)
    sections: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        report(index / (len(chunks) + 1), f"Summarising part {index} of {len(chunks)}…")
        sections.append(
            provider.complete(
                [{
                    "role": "user",
                    "content": SECTION_TEMPLATE.format(
                        index=index, total=len(chunks), transcript=transcript_lines(chunk)
                    ),
                }],
                system=SYSTEM,
                max_tokens=2048,
                temperature=0.3,
            ).strip()
        )

    report(0.9, "Merging sections…")
    return strip_empty_sections(
        provider.complete(
            [{
                "role": "user",
                "content": MERGE_TEMPLATE.format(
                    course=course_name,
                    title=lecture_title,
                    sections="\n\n---\n\n".join(sections),
                ),
            }],
            system=SYSTEM,
            max_tokens=4096,
            temperature=0.3,
        )
    )


def run_job(job) -> None:
    """Job handler: summarise a lecture and store the result as a Note."""
    from . import jobs

    with Session(engine) as session:
        lecture = session.get(Lecture, job.lecture_id)
        if lecture is None:
            jobs.fail(job, "Lecture no longer exists")
            return
        course = session.get(Course, lecture.course_id)
        transcript = session.exec(
            select(Transcript).where(Transcript.lecture_id == job.lecture_id)
        ).first()
        title = lecture.title
        course_name = course.name if course else ""

    if transcript is None or not transcript.full_text.strip():
        jobs.fail(job, "Transcribe this lecture before generating notes")
        return

    provider_name = job.params.get("provider") or ""
    model = job.params.get("model") or ""
    provider = (
        get_provider(provider_name, model)
        if provider_name
        else get_provider_for_task("summarize")
    )
    if not provider.available():
        jobs.fail(
            job,
            f"Provider '{provider.name}' is not available — check its API key in .env "
            "or that Ollama is running.",
        )
        return

    segments = json.loads(transcript.segments_json or "[]")
    if not segments:  # a transcript with no timing info still summarises fine
        segments = [{"start": 0.0, "end": 0.0, "text": transcript.full_text}]

    markdown = generate_markdown(
        provider,
        course_name,
        title,
        segments,
        progress_cb=lambda f, m: jobs.update(job, progress=f, message=m),
    )
    if not markdown:
        jobs.fail(job, f"{provider.name} returned an empty response")
        return

    used = f"{provider.name}/{provider.model}"
    with Session(engine) as session:
        note = Note(
            lecture_id=job.lecture_id,
            kind="summary",
            content_md=markdown,
            provider_used=used,
        )
        session.add(note)
        session.commit()
        session.refresh(note)
        note_id = note.id

    jobs.finish(job, f"Notes generated with {used}", result_id=note_id)
