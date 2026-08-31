// Typed fetch client for the TranscribeAI backend (/api is proxied by Vite in dev).

export interface Health {
  status: string
  providers: Record<string, boolean> // claude / openai / ollama -> usable now
  cuda: boolean
  tasks: Record<string, { provider: string; model: string }>
  transcription_model: string
  ffmpeg: boolean
  queue_depth: number
}

export interface Course {
  id: number
  name: string
  code: string
  term: string
  created_at: string
  lecture_count: number
}

export type LectureStatus = 'recorded' | 'transcribing' | 'ready' | 'failed'

export interface Lecture {
  id: number
  course_id: number
  title: string
  lecture_date: string | null
  status: LectureStatus
  duration_seconds: number | null
  created_at: string
  has_audio: boolean
  has_transcript: boolean
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  lecture_id: number
  full_text: string
  segments: Segment[]
  language: string
  model_used: string
  created_at: string
}

export interface Job {
  lecture_id: number
  status: 'none' | 'queued' | 'running' | 'done' | 'failed'
  progress: number
  message: string
  error: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!res.ok) {
    // FastAPI puts the human-readable reason in `detail`.
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${res.status} ${res.statusText} on ${path}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** Uploads go through XHR rather than fetch — a lecture recording is tens of
 *  megabytes and fetch can't report upload progress. */
function upload(
  path: string,
  file: Blob,
  filename: string,
  onProgress?: (fraction: number) => void,
): Promise<Lecture> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file, filename)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api${path}`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        let message = `Upload failed (${xhr.status})`
        try {
          message = JSON.parse(xhr.responseText).detail ?? message
        } catch {
          /* non-JSON error body */
        }
        reject(new Error(message))
      }
    }
    xhr.onerror = () => reject(new Error('Upload failed — is the backend running?'))
    xhr.send(form)
  })
}

export const api = {
  health: () => request<Health>('/health'),

  listCourses: () => request<Course[]>('/courses'),
  createCourse: (body: { name: string; code?: string; term?: string }) =>
    request<Course>('/courses', { method: 'POST', body: JSON.stringify(body) }),
  updateCourse: (id: number, body: Partial<Pick<Course, 'name' | 'code' | 'term'>>) =>
    request<Course>(`/courses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteCourse: (id: number) => request<void>(`/courses/${id}`, { method: 'DELETE' }),

  listLectures: (courseId: number) => request<Lecture[]>(`/lectures?course_id=${courseId}`),
  getLecture: (id: number) => request<Lecture>(`/lectures/${id}`),
  createLecture: (body: { course_id: number; title: string; lecture_date?: string | null }) =>
    request<Lecture>('/lectures', { method: 'POST', body: JSON.stringify(body) }),
  updateLecture: (id: number, body: { title?: string; lecture_date?: string | null }) =>
    request<Lecture>(`/lectures/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteLecture: (id: number) => request<void>(`/lectures/${id}`, { method: 'DELETE' }),

  uploadAudio: (id: number, file: Blob, filename: string, onProgress?: (f: number) => void) =>
    upload(`/lectures/${id}/audio`, file, filename, onProgress),
  transcribe: (id: number) => request<Job>(`/lectures/${id}/transcribe`, { method: 'POST' }),
  job: (id: number) => request<Job>(`/lectures/${id}/job`),
  transcript: (id: number) => request<Transcript>(`/lectures/${id}/transcript`),

  audioUrl: (id: number) => `/api/lectures/${id}/audio`,
  transcriptTextUrl: (id: number, timestamps: boolean) =>
    `/api/lectures/${id}/transcript.txt?timestamps=${timestamps}`,
}
