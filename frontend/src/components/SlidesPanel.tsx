import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type SlideDeck } from '../api'

export default function SlidesPanel({
  lectureId,
  onChanged,
}: {
  lectureId: number
  onChanged?: () => void
}) {
  const [decks, setDecks] = useState<SlideDeck[] | null>(null)
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      setDecks(await api.listSlides(lectureId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [lectureId])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // allow re-picking the same file
    if (!file) return

    setError(null)
    setUploadPct(0)
    try {
      await api.uploadSlides(lectureId, file, file.name, setUploadPct)
      await refresh()
      onChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploadPct(null)
    }
  }

  async function remove(deck: SlideDeck) {
    try {
      await api.deleteSlideDeck(deck.id)
      setConfirmId(null)
      await refresh()
      onChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <section className="slides-panel">
      <div className="row">
        <button
          className="primary"
          onClick={() => fileRef.current?.click()}
          disabled={uploadPct !== null}
        >
          Add slides
        </button>
        <span className="muted small">
          PDF or PowerPoint. Slide text is included when notes are generated.
        </span>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.pptx,.ppt,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
          hidden
          onChange={onPick}
        />
      </div>

      {error && <p className="error">{error}</p>}

      {uploadPct !== null && (
        <div className="progress-box">
          <div className="progress">
            <div className="progress-fill" style={{ width: `${uploadPct * 100}%` }} />
          </div>
          <p className="muted small">Uploading and extracting text…</p>
        </div>
      )}

      {decks && decks.length === 0 && (
        <p className="muted">
          No slides attached. Adding the lecturer's deck helps the notes get technical
          terms and notation right, since speech recognition often mangles them. A
          PowerPoint file also brings its speaker notes, which a PDF export drops.
        </p>
      )}

      <ul className="deck-list">
        {decks?.map((deck) => (
          <li key={deck.id}>
            <span className="deck-name">{deck.filename}</span>
            <span className="muted small">
              {deck.page_count} slide{deck.page_count === 1 ? '' : 's'}
            </span>
            {!deck.has_text && (
              <span className="badge failed" title="pypdf cannot read text from images">
                no text
              </span>
            )}
            <a className="button-link" href={api.slidePdfUrl(deck.id)} target="_blank" rel="noreferrer">
              Open
            </a>
            <a className="button-link" href={api.slideTextUrl(deck.id)} target="_blank" rel="noreferrer">
              Text
            </a>
            {confirmId === deck.id ? (
              <>
                <button className="danger" onClick={() => remove(deck)}>
                  Delete
                </button>
                <button onClick={() => setConfirmId(null)}>Cancel</button>
              </>
            ) : (
              <button className="danger-ghost" onClick={() => setConfirmId(deck.id)}>
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>

      {decks?.some((d) => !d.has_text) && (
        <p className="muted small">
          A deck marked “no text” is a scan or an export of images. Nothing can be read
          from it without OCR, so it will not reach the notes.
        </p>
      )}
    </section>
  )
}
