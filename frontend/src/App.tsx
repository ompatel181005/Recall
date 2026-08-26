import { useEffect, useState } from 'react'
import { api, type Health } from './api'
import './App.css'

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`dot ${ok ? 'ok' : 'down'}`} aria-hidden="true" />
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="brand">TranscribeAI</h1>
        <p className="muted">
          Courses appear here once milestone M1 (Record &amp; Transcribe) is
          built.
        </p>
      </aside>

      <main className="main">
        <h2>System status</h2>

        {error && (
          <p className="error">
            Backend unreachable ({error}). Start it with{' '}
            <code>uvicorn app.main:app --reload --port 8000</code> in{' '}
            <code>backend/</code>.
          </p>
        )}

        {!health && !error && <p className="muted">Checking backend…</p>}

        {health && (
          <>
            <ul className="status-list">
              <li>
                <StatusDot ok={health.status === 'ok'} /> Backend connected
              </li>
              <li>
                <StatusDot ok={health.cuda} /> GPU (CUDA) for transcription —
                model <code>{health.transcription_model}</code>
              </li>
              {Object.entries(health.providers).map(([name, ok]) => (
                <li key={name}>
                  <StatusDot ok={ok} /> Provider: {name}
                </li>
              ))}
            </ul>

            <h2>Task routing (config.yaml)</h2>
            <ul className="status-list">
              {Object.entries(health.tasks).map(([task, cfg]) => (
                <li key={task}>
                  <code>{task}</code> → {cfg.provider} / {cfg.model}
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  )
}

export default App
