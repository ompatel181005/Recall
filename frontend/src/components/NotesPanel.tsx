import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type Job, type Note, type ProviderOption } from '../api'

/** Turn `[MM:SS]` into a button that seeks the audio, so a note can be traced
 *  back to what the lecturer actually said. */
function renderMarkdown(markdown: string): string {
  const linked = markdown.replace(
    /\[(\d{1,3}):([0-5]\d)\]/g,
    (_match, minutes: string, seconds: string) =>
      `<button class="stamp-link" data-seek="${Number(minutes) * 60 + Number(seconds)}">` +
      `${minutes}:${seconds}</button>`,
  )
  return DOMPurify.sanitize(marked.parse(linked, { async: false }) as string, {
    ADD_ATTR: ['data-seek'],
  })
}

function optionLabel(option: ProviderOption): string {
  return `${option.provider} / ${option.model}${option.is_default ? ' (default)' : ''}`
}

export default function NotesPanel({
  lectureId,
  job,
  onGenerate,
  onSeek,
}: {
  lectureId: number
  job: Job | null
  onGenerate: () => void
  onSeek: (seconds: number) => void
}) {
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [options, setOptions] = useState<ProviderOption[]>([])
  const [choice, setChoice] = useState('')      // "provider|model", '' = config default
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const running = job != null && (job.status === 'queued' || job.status === 'running')
  const anyAvailable = options.some((o) => o.available)

  const refresh = useCallback(async () => {
    try {
      const next = await api.listNotes(lectureId)
      setNotes(next)
      setSelectedId((current) =>
        current != null && next.some((n) => n.id === current) ? current : (next[0]?.id ?? null),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [lectureId])

  useEffect(() => {
    refresh()
    api
      .taskProviders('summarize')
      .then((next) => {
        setOptions(next)
        // Don't hand the user a preselected model that can't run — if the
        // configured default has no key (or Ollama is down), start on
        // whichever alternative actually works.
        const preferred = next.find((o) => o.is_default)
        if (!preferred?.available) {
          const usable = next.find((o) => o.available)
          if (usable) setChoice(`${usable.provider}|${usable.model}`)
        }
      })
      .catch(() => setOptions([]))
  }, [refresh])

  // A finished run means there's a new note to pick up.
  useEffect(() => {
    if (job?.status === 'done') refresh()
  }, [job?.status, job?.result_id, refresh])

  const selected = useMemo(
    () => notes?.find((n) => n.id === selectedId) ?? null,
    [notes, selectedId],
  )

  const html = useMemo(
    () => (selected ? renderMarkdown(selected.content_md) : ''),
    [selected],
  )

  async function generate() {
    setError(null)
    const [provider = '', model = ''] = choice ? choice.split('|') : []
    try {
      await api.generateNotes(lectureId, provider, model)
      onGenerate()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function save() {
    if (!selected || draft == null) return
    try {
      await api.updateNote(selected.id, draft)
      setDraft(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function remove(note: Note) {
    try {
      await api.deleteNote(note.id)
      setDraft(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function handleClick(event: React.MouseEvent<HTMLDivElement>) {
    const stamp = (event.target as HTMLElement).closest('[data-seek]')
    if (stamp) onSeek(Number(stamp.getAttribute('data-seek')))
  }

  return (
    <section className="notes-panel">
      <div className="notes-controls">
        <label className="field">
          <span>Model</span>
          <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={running}>
            {options.map((option) => (
              <option
                key={`${option.provider}|${option.model}`}
                value={option.is_default ? '' : `${option.provider}|${option.model}`}
                disabled={!option.available}
              >
                {optionLabel(option)}
                {option.available ? '' : ' — unavailable'}
              </option>
            ))}
          </select>
        </label>
        <button className="primary" onClick={generate} disabled={running || !anyAvailable}>
          {notes && notes.length > 0 ? 'Generate again' : 'Generate notes'}
        </button>
      </div>

      {options.length > 0 && !anyAvailable && (
        <p className="muted small">
          No summarisation model is reachable. Add an API key to <code>.env</code>, or
          start Ollama and pull the model named in <code>config.yaml</code>.
        </p>
      )}

      {error && <p className="error">{error}</p>}

      {running && (
        <div className="progress-box">
          <div className="progress">
            <div className="progress-fill" style={{ width: `${(job?.progress ?? 0) * 100}%` }} />
          </div>
          <p className="muted small">{job?.message}</p>
        </div>
      )}

      {job?.status === 'failed' && <p className="error">{job.error}</p>}

      {notes && notes.length === 0 && !running && (
        <p className="muted">
          No notes yet. Generating with a second model adds a run rather than replacing
          the first, so you can compare them.
        </p>
      )}

      {notes && notes.length > 1 && (
        <div className="note-runs">
          {notes.map((note) => (
            <button
              key={note.id}
              className={`chip ${note.id === selectedId ? 'selected' : ''}`}
              onClick={() => {
                setSelectedId(note.id)
                setDraft(null)
              }}
            >
              {note.provider_used} · {new Date(note.created_at).toLocaleString()}
            </button>
          ))}
        </div>
      )}

      {selected && (
        <>
          <div className="note-head">
            <span className="muted small">
              {selected.provider_used} · {new Date(selected.created_at).toLocaleString()}
            </span>
            <span className="row">
              {draft == null ? (
                <button onClick={() => setDraft(selected.content_md)}>Edit</button>
              ) : (
                <>
                  <button className="primary" onClick={save}>
                    Save
                  </button>
                  <button onClick={() => setDraft(null)}>Cancel</button>
                </>
              )}
              <button className="danger-ghost" onClick={() => remove(selected)}>
                Delete
              </button>
            </span>
          </div>

          {draft == null ? (
            <div
              className="markdown"
              onClick={handleClick}
              // Sanitised above; timestamps are rewritten into seek buttons.
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : (
            <textarea
              className="note-editor"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck
            />
          )}
        </>
      )}
    </section>
  )
}
