import { useState } from 'react'
import { api, type Course } from '../api'

/** A Move button that opens a course picker for one lecture. */
export default function MoveLecture({
  lectureId,
  courseId,
  courses,
  onMoved,
}: {
  lectureId: number
  courseId: number
  courses: Course[]
  onMoved: (courseId: number) => void
}) {
  const others = courses.filter((c) => c.id !== courseId)
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (others.length === 0) return null

  async function move() {
    if (target == null) return
    setSaving(true)
    setError(null)
    try {
      await api.updateLecture(lectureId, { course_id: target })
      setOpen(false)
      onMoved(target)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <button
        className="move-button"
        onClick={() => {
          setTarget(others[0].id)
          setError(null)
          setOpen(true)
        }}
      >
        Move
      </button>
    )
  }

  return (
    <span className="move-lecture">
      <select
        value={target ?? ''}
        onChange={(e) => setTarget(Number(e.target.value))}
        disabled={saving}
        aria-label="Move to course"
      >
        {others.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <button className="primary" onClick={move} disabled={saving}>
        {saving ? 'Moving…' : 'Move'}
      </button>
      <button onClick={() => setOpen(false)} disabled={saving}>
        Cancel
      </button>
      {error && <span className="error small">{error}</span>}
    </span>
  )
}
