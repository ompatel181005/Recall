import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type ChatMessage, type Citation, type IndexStatus } from '../api'

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/** Render the answer, turning each [n] into a chip that opens the source. */
function renderAnswer(markdown: string, citations: Citation[]): string {
  const known = new Set(citations.map((c) => c.n))
  const linked = markdown.replace(/\[(\d{1,2})\]/g, (match, digits: string) => {
    const n = Number(digits)
    if (!known.has(n)) return match
    return `<button class="cite" data-cite="${n}">${n}</button>`
  })
  return DOMPurify.sanitize(marked.parse(linked, { async: false }) as string, {
    ADD_ATTR: ['data-cite'],
  })
}

function sourceLabel(citation: Citation): string {
  return citation.source === 'slides'
    ? citation.slide_label || 'slides'
    : clock(citation.start_seconds ?? 0)
}

export default function TutorPanel({
  courseId,
  onOpenLecture,
}: {
  courseId: number
  onOpenLecture: (lectureId: number, seconds: number | null) => void
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [status, setStatus] = useState<IndexStatus | null>(null)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const [history, indexed] = await Promise.all([
        api.chatHistory(courseId),
        api.indexStatus(courseId),
      ])
      setMessages(history)
      setStatus(indexed)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [courseId])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, asking])

  const ready = (status?.chunks ?? 0) > 0

  const unindexed = useMemo(() => {
    if (!status) return 0
    return Math.max(status.total_lectures - status.indexed_lectures, 0)
  }, [status])

  async function send() {
    const text = question.trim()
    if (!text || asking) return

    // Show the question immediately; the backend stores it either way.
    const optimistic: ChatMessage = {
      id: -Date.now(),
      course_id: courseId,
      role: 'user',
      content: text,
      citations: [],
      created_at: new Date().toISOString(),
    }
    setMessages((current) => [...current, optimistic])
    setQuestion('')
    setAsking(true)
    setError(null)

    try {
      const answer = await api.ask(courseId, text)
      setMessages((current) => [...current, answer])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setMessages((current) => current.filter((m) => m.id !== optimistic.id))
      setQuestion(text) // hand the question back rather than losing it
    } finally {
      setAsking(false)
    }
  }

  async function clear() {
    try {
      await api.clearChat(courseId)
      setConfirmClear(false)
      setMessages([])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function reindex() {
    try {
      await api.reindexCourse(courseId)
      setTimeout(refresh, 1500)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function onAnswerClick(event: React.MouseEvent<HTMLDivElement>, citations: Citation[]) {
    const chip = (event.target as HTMLElement).closest('[data-cite]')
    if (!chip) return
    const n = Number(chip.getAttribute('data-cite'))
    const citation = citations.find((c) => c.n === n)
    if (citation) onOpenLecture(citation.lecture_id, citation.start_seconds)
  }

  return (
    <section className="tutor">
      <div className="tutor-head">
        <span className="muted small">
          {status
            ? `${status.indexed_lectures} of ${status.total_lectures} lectures searchable · ${status.chunks} passages`
            : 'Checking index…'}
          {unindexed > 0 && ' — transcribe the rest to include them'}
        </span>
        <span className="row">
          <button onClick={reindex}>Re-index</button>
          {confirmClear ? (
            <>
              <button className="danger" onClick={clear}>
                Clear chat
              </button>
              <button onClick={() => setConfirmClear(false)}>Cancel</button>
            </>
          ) : (
            messages.length > 0 && (
              <button className="danger-ghost" onClick={() => setConfirmClear(true)}>
                Clear
              </button>
            )
          )}
        </span>
      </div>

      {error && <p className="error">{error}</p>}

      {!ready && (
        <p className="muted">
          Nothing is indexed for this course yet. Transcribe a lecture and it becomes
          searchable automatically.
        </p>
      )}

      <div className="chat">
        {messages.length === 0 && ready && (
          <p className="muted">
            Ask anything covered in this course — “what did she say about aliasing?”,
            “explain the region of convergence”. Answers cite the lecture and time they
            came from, and the citations are clickable.
          </p>
        )}

        {messages.map((message) =>
          message.role === 'user' ? (
            <div key={message.id} className="turn user">
              {message.content}
            </div>
          ) : (
            <div key={message.id} className="turn assistant">
              <div
                className="markdown"
                onClick={(e) => onAnswerClick(e, message.citations)}
                // Sanitised in renderAnswer; [n] becomes a source button.
                dangerouslySetInnerHTML={{
                  __html: renderAnswer(message.content, message.citations),
                }}
              />
              {message.citations.some((c) => c.cited) && (
                <ol className="sources">
                  {message.citations
                    .filter((c) => c.cited)
                    .map((citation) => (
                      <li key={citation.n}>
                        <button
                          className="source-link"
                          onClick={() =>
                            onOpenLecture(citation.lecture_id, citation.start_seconds)
                          }
                        >
                          [{citation.n}] {citation.lecture_title} · {sourceLabel(citation)}
                        </button>
                      </li>
                    ))}
                </ol>
              )}
            </div>
          ),
        )}

        {asking && <div className="turn assistant muted">Searching the course…</div>}
        <div ref={endRef} />
      </div>

      <div className="ask">
        <input
          placeholder={ready ? 'Ask about this course…' : 'Nothing indexed yet'}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          disabled={!ready || asking}
          aria-label="Question"
        />
        <button className="primary" onClick={send} disabled={!ready || asking || !question.trim()}>
          Ask
        </button>
      </div>
    </section>
  )
}
