import { useCallback, useEffect, useRef, useState } from 'react'

type Source = 'mic' | 'system' | 'both'

const SOURCE_LABELS: Record<Source, string> = {
  mic: 'Microphone (in-person lecture)',
  system: 'Tab / screen audio (online lecture)',
  both: 'Both mixed (online lecture + room)',
}

function pickMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  return candidates.find((t) => MediaRecorder.isTypeSupported(t)) ?? ''
}

function formatClock(seconds: number): string {
  const s = Math.floor(seconds)
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hh > 0 ? `${hh}:${pad(mm)}:${pad(ss)}` : `${pad(mm)}:${pad(ss)}`
}

export default function Recorder({
  onRecorded,
  disabled,
}: {
  onRecorded: (blob: Blob, filename: string) => void
  disabled?: boolean
}) {
  const [source, setSource] = useState<Source>('mic')
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [deviceId, setDeviceId] = useState<string>('')
  const [state, setState] = useState<'idle' | 'recording' | 'paused'>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamsRef = useRef<MediaStream[]>([])
  const audioCtxRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)
  const startedAtRef = useRef(0)
  const pausedTotalRef = useRef(0)
  const pausedAtRef = useRef(0)

  const loadDevices = useCallback(async () => {
    try {
      // Labels stay blank until the page has been granted mic access once.
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true })
      probe.getTracks().forEach((t) => t.stop())
      const all = await navigator.mediaDevices.enumerateDevices()
      setDevices(all.filter((d) => d.kind === 'audioinput'))
    } catch {
      setError('Microphone permission denied — allow it in the browser to record.')
    }
  }, [])

  const cleanup = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    streamsRef.current.forEach((s) => s.getTracks().forEach((t) => t.stop()))
    streamsRef.current = []
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    recorderRef.current = null
    setLevel(0)
  }, [])

  useEffect(() => cleanup, [cleanup])

  // Tick the elapsed clock while recording.
  useEffect(() => {
    if (state !== 'recording') return
    const id = setInterval(() => {
      setElapsed((Date.now() - startedAtRef.current - pausedTotalRef.current) / 1000)
    }, 250)
    return () => clearInterval(id)
  }, [state])

  async function start() {
    setError(null)
    try {
      const context = new AudioContext()
      const destination = context.createMediaStreamDestination()
      const analyser = context.createAnalyser()
      analyser.fftSize = 512

      if (source === 'mic' || source === 'both') {
        const mic = await navigator.mediaDevices.getUserMedia({
          audio: {
            deviceId: deviceId ? { exact: deviceId } : undefined,
            echoCancellation: false, // a lecture hall is not a phone call
            noiseSuppression: false, // keeps quiet speech from being gated out
            autoGainControl: true,
          },
        })
        streamsRef.current.push(mic)
        const node = context.createMediaStreamSource(mic)
        node.connect(destination)
        node.connect(analyser)
      }

      if (source === 'system' || source === 'both') {
        // Chrome only offers tab/system audio alongside a video request.
        const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
        streamsRef.current.push(display)
        display.getVideoTracks().forEach((t) => t.stop()) // audio only — no screen is stored
        if (display.getAudioTracks().length === 0) {
          cleanup()
          setError('No audio was shared. Re-share and tick "Share tab audio" / "Share system audio".')
          return
        }
        const node = context.createMediaStreamSource(display)
        node.connect(destination)
        node.connect(analyser)
      }

      audioCtxRef.current = context

      const buffer = new Uint8Array(analyser.frequencyBinCount)
      const meter = () => {
        analyser.getByteTimeDomainData(buffer)
        let peak = 0
        for (const v of buffer) peak = Math.max(peak, Math.abs(v - 128) / 128)
        setLevel(peak)
        rafRef.current = requestAnimationFrame(meter)
      }
      meter()

      const recorder = new MediaRecorder(destination.stream, { mimeType: pickMimeType() })
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const type = recorder.mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type })
        const extension = type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm'
        cleanup()
        if (blob.size > 0) onRecorded(blob, `recording.${extension}`)
      }
      // Flush every second so a crash mid-lecture doesn't lose everything.
      recorder.start(1000)
      recorderRef.current = recorder

      startedAtRef.current = Date.now()
      pausedTotalRef.current = 0
      setElapsed(0)
      setState('recording')
    } catch (e) {
      cleanup()
      setError(e instanceof Error ? e.message : 'Could not start recording')
    }
  }

  function pause() {
    recorderRef.current?.pause()
    pausedAtRef.current = Date.now()
    setState('paused')
  }

  function resume() {
    recorderRef.current?.resume()
    pausedTotalRef.current += Date.now() - pausedAtRef.current
    setState('recording')
  }

  function stop() {
    recorderRef.current?.stop() // onstop hands the blob up and cleans up
    setState('idle')
  }

  return (
    <div className="recorder">
      {state === 'idle' ? (
        <>
          <label className="field">
            <span>Source</span>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as Source)}
              disabled={disabled}
            >
              {Object.entries(SOURCE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          {source !== 'system' && (
            <label className="field">
              <span>Input device</span>
              <select
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                onFocus={() => devices.length === 0 && loadDevices()}
                disabled={disabled}
              >
                <option value="">System default</option>
                {devices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label || 'Unnamed input'}
                  </option>
                ))}
              </select>
            </label>
          )}

          <button className="primary" onClick={start} disabled={disabled}>
            ● Start recording
          </button>
        </>
      ) : (
        <>
          <div className="rec-status">
            <span className={`rec-dot ${state === 'recording' ? 'live' : ''}`} />
            <strong className="clock">{formatClock(elapsed)}</strong>
            <span className="muted">{state === 'paused' ? 'Paused' : 'Recording'}</span>
          </div>

          <div className="meter" aria-hidden="true">
            <div className="meter-fill" style={{ width: `${Math.min(level * 140, 100)}%` }} />
          </div>

          <div className="row">
            {state === 'recording' ? (
              <button onClick={pause}>❚❚ Pause</button>
            ) : (
              <button onClick={resume}>▶ Resume</button>
            )}
            <button className="primary" onClick={stop}>
              ■ Stop &amp; transcribe
            </button>
          </div>
        </>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}
