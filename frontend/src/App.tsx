import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type Course, type Health, type Lecture } from './api'
import LectureDetail from './components/LectureDetail'
import Recorder from './components/Recorder'
import './App.css'

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`dot ${ok ? 'ok' : 'down'}`} aria-hidden="true" />
}

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const pad = (n: number) => String(n).padStart(2, '0')
  const hh = Math.floor(s / 3600)
  return hh > 0
    ? `${hh}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`
    : `${pad(Math.floor(s / 60))}:${pad(s % 60)}`
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [showStatus, setShowStatus] = useState(false)

  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState<number | null>(null)
  const [newCourse, setNewCourse] = useState('')

  const [lectures, setLectures] = useState<Lecture[]>([])
  const [lectureId, setLectureId] = useState<number | null>(null)

  const [confirmDeleteCourse, setConfirmDeleteCourse] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const refreshHealth = useCallback(() => {
    api.health().then(setHealth).catch((e: Error) => setHealthError(e.message))
  }, [])

  const refreshCourses = useCallback(async () => {
    try {
      const next = await api.listCourses()
      setCourses(next)
      setCourseId((current) => current ?? next[0]?.id ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  /** Switching course always drops back to that course's lecture list. */
  const selectCourse = useCallback((id: number) => {
    setLectureId(null)
    setConfirmDeleteCourse(false)
    setCourseId(id)
  }, [])

  const refreshLectures = useCallback(async () => {
    if (courseId == null) return // nothing selected: the list is already empty
    try {
      setLectures(await api.listLectures(courseId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [courseId])

  useEffect(() => {
    refreshHealth()
    refreshCourses()
  }, [refreshHealth, refreshCourses])

  useEffect(() => {
    refreshLectures()
  }, [refreshLectures])

  // Keep status badges live while anything is on the GPU queue.
  const anyTranscribing = lectures.some((l) => l.status === 'transcribing')
  useEffect(() => {
    if (!anyTranscribing) return
    const id = setInterval(refreshLectures, 2000)
    return () => clearInterval(id)
  }, [anyTranscribing, refreshLectures])

  const course = courses.find((c) => c.id === courseId) ?? null
  const lecture = lectures.find((l) => l.id === lectureId) ?? null

  const defaultTitle = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    return `Lecture ${lectures.length + 1} — ${today}`
  }, [lectures.length])

  async function addCourse() {
    const name = newCourse.trim()
    if (!name) return
    try {
      const created = await api.createCourse({ name })
      setNewCourse('')
      await refreshCourses()
      selectCourse(created.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  /** Shared by the recorder and the file picker: make the lecture row, push the
   *  audio, and let the backend queue transcription. */
  async function ingest(blob: Blob, filename: string) {
    if (courseId == null) return
    setError(null)
    setUploadPct(0)
    try {
      const created = await api.createLecture({
        course_id: courseId,
        title: newTitle.trim() || defaultTitle,
        lecture_date: new Date().toISOString().slice(0, 10),
      })
      await api.uploadAudio(created.id, blob, filename, setUploadPct)
      setNewTitle('')
      await Promise.all([refreshLectures(), refreshCourses()])
      setLectureId(created.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploadPct(null)
    }
  }

  function onPickFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) void ingest(file, file.name)
    event.target.value = '' // allow re-picking the same file
  }

  async function removeCourse() {
    if (courseId == null) return
    try {
      await api.deleteCourse(courseId)
      setConfirmDeleteCourse(false)
      setCourseId(null)
      setLectureId(null)
      setLectures([])
      await refreshCourses()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const onLectureChanged = useCallback(async () => {
    await refreshLectures()
  }, [refreshLectures])

  const onLectureDeleted = useCallback(async () => {
    setLectureId(null)
    await Promise.all([refreshLectures(), refreshCourses()])
  }, [refreshLectures, refreshCourses])

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="brand">TranscribeAI</h1>

        <nav className="course-list">
          {courses.map((c) => (
            <button
              key={c.id}
              className={`course-item ${c.id === courseId ? 'selected' : ''}`}
              onClick={() => selectCourse(c.id)}
            >
              <span className="course-name">{c.name}</span>
              <span className="count">{c.lecture_count}</span>
            </button>
          ))}
          {courses.length === 0 && <p className="muted small">No courses yet.</p>}
        </nav>

        <div className="add-course">
          <input
            placeholder="New course…"
            value={newCourse}
            onChange={(e) => setNewCourse(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addCourse()}
            aria-label="New course name"
          />
          <button onClick={addCourse}>Add</button>
        </div>

        <div className="sidebar-foot">
          <button className="link" onClick={() => setShowStatus((v) => !v)}>
            {showStatus ? '▾' : '▸'} System status
          </button>
          {showStatus && (
            <ul className="status-list small">
              <li>
                <StatusDot ok={!!health && !healthError} /> Backend
              </li>
              <li>
                <StatusDot ok={!!health?.cuda} /> GPU · {health?.transcription_model}
              </li>
              <li>
                <StatusDot ok={!!health?.ffmpeg} /> ffmpeg
              </li>
              {health &&
                Object.entries(health.providers).map(([name, ok]) => (
                  <li key={name}>
                    <StatusDot ok={ok} /> {name}
                  </li>
                ))}
            </ul>
          )}
          {healthError && (
            <p className="error small">
              Backend unreachable. Start it with{' '}
              <code>uvicorn app.main:app --reload --port 8000</code>.
            </p>
          )}
        </div>
      </aside>

      <main className="main">
        {error && <p className="error">{error}</p>}

        {!course && <p className="muted">Create a course to get started.</p>}

        {course && lecture && (
          <>
            <button className="link" onClick={() => setLectureId(null)}>
              ← {course.name}
            </button>
            <LectureDetail
              key={lecture.id}
              lecture={lecture}
              onChanged={onLectureChanged}
              onDeleted={onLectureDeleted}
            />
          </>
        )}

        {course && !lecture && (
          <>
            <div className="course-head">
              <h2>{course.name}</h2>
              {confirmDeleteCourse ? (
                <span className="row">
                  <span className="muted small">
                    Delete “{course.name}” and all {course.lecture_count} lectures?
                    Recordings move to <code>data/.trash</code>.
                  </span>
                  <button className="danger" onClick={removeCourse}>
                    Yes, delete
                  </button>
                  <button onClick={() => setConfirmDeleteCourse(false)}>Cancel</button>
                </span>
              ) : (
                <button className="danger-ghost" onClick={() => setConfirmDeleteCourse(true)}>
                  Delete course
                </button>
              )}
            </div>

            <section className="capture">
              <label className="field">
                <span>Lecture title</span>
                <input
                  placeholder={defaultTitle}
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                />
              </label>

              <Recorder onRecorded={ingest} disabled={uploadPct !== null} />

              <div className="import">
                <button onClick={() => fileRef.current?.click()} disabled={uploadPct !== null}>
                  Import audio or video file
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="audio/*,video/*"
                  hidden
                  onChange={onPickFile}
                />
              </div>

              {uploadPct !== null && (
                <div className="progress-box">
                  <div className="progress">
                    <div className="progress-fill" style={{ width: `${uploadPct * 100}%` }} />
                  </div>
                  <p className="muted small">Uploading… {Math.round(uploadPct * 100)}%</p>
                </div>
              )}
            </section>

            <h2>Lectures</h2>
            {lectures.length === 0 && <p className="muted">Nothing recorded yet.</p>}
            <ul className="lecture-list">
              {lectures.map((l) => (
                <li key={l.id}>
                  <button className="lecture-item" onClick={() => setLectureId(l.id)}>
                    <span className="lecture-title">{l.title}</span>
                    <span className={`badge ${l.status}`}>{l.status}</span>
                    {l.duration_seconds != null && (
                      <span className="muted small">{formatClock(l.duration_seconds)}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  )
}
