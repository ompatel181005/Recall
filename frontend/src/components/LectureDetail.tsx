import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type LectureJobs, type Lecture, type Transcript } from '../api'
import NotesPanel from './NotesPanel'
import SlidesPanel from './SlidesPanel'

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hh > 0 ? `${hh}:${pad(mm)}:${pad(ss)}` : `${pad(mm)}:${pad(ss)}`
}

export default function LectureDetail({
  lecture,
  onChanged,
  onDeleted,
}: {
  lecture: Lecture
  onChanged: () => void
  onDeleted: () => void
}) {
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [jobs, setJobs] = useState<LectureJobs | null>(null)
  const [tab, setTab] = useState<'transcript' | 'notes' | 'slides'>('transcript')
  const [currentTime, setCurrentTime] = useState(0)
  const [query, setQuery] = useState('')
  const [title, setTitle] = useState(lecture.title)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)

  // Load the transcript whenever this lecture has one. App keys this component
  // by lecture id, so per-lecture state resets on its own — no sync needed here.
  useEffect(() => {
    if (!lecture.has_transcript) return
    let cancelled = false
    api
      .transcript(lecture.id)
      .then((t) => !cancelled && setTranscript(t))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [lecture.id, lecture.has_transcript, lecture.status])

  const notesRunning =
    jobs?.notes.status === 'queued' || jobs?.notes.status === 'running'
  const busy = lecture.status === 'transcribing' || notesRunning

  const pollJobs = useCallback(async () => {
    try {
      return await api.jobs(lecture.id)
    } catch {
      return null // backend restarting — the next tick picks it up
    }
  }, [lecture.id])

  // One poll covers both lanes: transcription on the GPU and note generation.
  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      const next = await pollJobs()
      if (cancelled || !next) return
      setJobs(next)
      // The lecture row itself changes when transcription lands (status,
      // duration, has_transcript), so ask the parent to refetch it.
      const settled =
        next.transcribe.status === 'done' || next.transcribe.status === 'failed'
      if (lecture.status === 'transcribing' && settled) onChanged()
    }

    tick()
    const id = busy ? setInterval(tick, 1500) : undefined
    return () => {
      cancelled = true
      if (id) clearInterval(id)
    }
  }, [lecture.id, lecture.status, busy, pollJobs, onChanged])

  const segments = useMemo(() => {
    if (!transcript) return []
    const needle = query.trim().toLowerCase()
    if (!needle) return transcript.segments
    return transcript.segments.filter((s) => s.text.toLowerCase().includes(needle))
  }, [transcript, query])

  const activeIndex = useMemo(() => {
    if (!transcript) return -1
    return transcript.segments.findIndex((s) => currentTime >= s.start && currentTime < s.end)
  }, [transcript, currentTime])

  function seekTo(seconds: number) {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = seconds
    void audio.play()
  }

  async function rename() {
    const next = title.trim()
    if (!next || next === lecture.title) return
    try {
      await api.updateLecture(lecture.id, { title: next })
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function retranscribe() {
    try {
      setError(null)
      await api.transcribe(lecture.id)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const refreshJobs = useCallback(async () => {
    const next = await pollJobs()
    if (next) setJobs(next)
  }, [pollJobs])

  async function remove() {
    try {
      await api.deleteLecture(lecture.id)
      onDeleted()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function copyAll() {
    if (!transcript) return
    await navigator.clipboard.writeText(transcript.full_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <section className="lecture-detail">
      <header className="detail-head">
        <input
          className="title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={rename}
          onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
          aria-label="Lecture title"
        />
        <div className="row">
          <span className={`badge ${lecture.status}`}>{lecture.status}</span>
          {lecture.lecture_date && <span className="muted">{lecture.lecture_date}</span>}
          {lecture.duration_seconds != null && (
            <span className="muted">{formatClock(lecture.duration_seconds)}</span>
          )}
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      {lecture.has_audio && (
        <audio
          ref={audioRef}
          className="player"
          controls
          preload="metadata"
          src={api.audioUrl(lecture.id)}
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        />
      )}

      {lecture.status === 'transcribing' && (
        <div className="progress-box">
          <div className="progress">
            <div
              className="progress-fill"
              style={{ width: `${(jobs?.transcribe.progress ?? 0) * 100}%` }}
            />
          </div>
          <p className="muted">{jobs?.transcribe.message ?? 'Queued…'}</p>
        </div>
      )}

      {lecture.status === 'failed' && (
        <div className="progress-box">
          <p className="error">
            Transcription failed: {jobs?.transcribe.error || 'unknown error'}
          </p>
          <button onClick={retranscribe}>Try again</button>
        </div>
      )}

      {lecture.status === 'recorded' && lecture.has_audio && (
        <button className="primary" onClick={retranscribe}>
          Transcribe this lecture
        </button>
      )}

      <nav className="tabs">
        <button
          className={`tab ${tab === 'transcript' ? 'selected' : ''}`}
          onClick={() => setTab('transcript')}
        >
          Transcript
        </button>
        <button
          className={`tab ${tab === 'notes' ? 'selected' : ''}`}
          onClick={() => setTab('notes')}
        >
          Notes
          {notesRunning && <span className="tab-dot" aria-label="generating" />}
        </button>
        <button
          className={`tab ${tab === 'slides' ? 'selected' : ''}`}
          onClick={() => setTab('slides')}
        >
          Slides
        </button>
      </nav>

      {tab === 'notes' &&
        (lecture.has_transcript ? (
          <NotesPanel
            lectureId={lecture.id}
            job={jobs?.notes ?? null}
            onGenerate={refreshJobs}
            onSeek={seekTo}
          />
        ) : (
          <p className="muted">Transcribe this lecture before generating notes.</p>
        ))}

      {/* Slides can go on before the audio is transcribed — often they're
          available before the lecture is even recorded. */}
      {tab === 'slides' && <SlidesPanel lectureId={lecture.id} />}

      {tab === 'transcript' && !lecture.has_transcript && (
        <p className="muted">No transcript yet.</p>
      )}

      {tab === 'transcript' && transcript && (
        <>
          <div className="transcript-tools">
            <input
              type="search"
              placeholder="Search this transcript…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button onClick={copyAll}>{copied ? 'Copied ✓' : 'Copy text'}</button>
            <a className="button-link" href={api.transcriptTextUrl(lecture.id, true)} download>
              Export .txt
            </a>
            <button onClick={retranscribe}>Re-transcribe</button>
          </div>

          <p className="muted small">
            {transcript.segments.length} segments · {transcript.language} ·{' '}
            {transcript.model_used}
            {query && ` · ${segments.length} matching`}
          </p>

          <ol className="segments">
            {segments.map((seg) => {
              const isActive = transcript.segments[activeIndex] === seg
              return (
                <li key={`${seg.start}-${seg.end}`} className={isActive ? 'active' : ''}>
                  <button className="stamp" onClick={() => seekTo(seg.start)}>
                    {formatClock(seg.start)}
                  </button>
                  <span>{seg.text}</span>
                </li>
              )
            })}
          </ol>
        </>
      )}

      {!lecture.has_audio && (
        <p className="muted">No audio attached yet — record or import a file from the course page.</p>
      )}

      <footer className="detail-foot">
        {confirmDelete ? (
          <span className="row">
            <span className="muted small">
              Delete this lecture? Its audio and text move to <code>data/.trash</code>.
            </span>
            <button className="danger" onClick={remove}>
              Yes, delete
            </button>
            <button onClick={() => setConfirmDelete(false)}>Cancel</button>
          </span>
        ) : (
          <button className="danger-ghost" onClick={() => setConfirmDelete(true)}>
            Delete lecture
          </button>
        )}
      </footer>
    </section>
  )
}
