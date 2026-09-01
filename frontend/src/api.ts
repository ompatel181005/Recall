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
  id?: string
  kind?: string
  lecture_id?: number
  status: 'none' | 'queued' | 'running' | 'done' | 'failed'
  progress: number
  message: string
  error: string
  result_id?: number | null
}

/** One entry per job kind — a single poll covers transcription and notes. */
export interface LectureJobs {
  transcribe: Job
  notes: Job
}

export interface Note {
  id: number
  lecture_id: number
  kind: string
  content_md: string
  provider_used: string
  created_at: string
}

export interface SlideDeck {
  id: number
  lecture_id: number
  filename: string
  page_count: number
  has_text: boolean
  created_at: string
}

/** A provider/model this task can run on, from config.yaml. */
export interface ProviderOption {
  provider: string
  model: string
  is_default: boolean
  available: boolean
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
function upload<T>(
  path: string,
  file: Blob,
  filename: string,
  onProgress?: (fraction: number) => void,
): Promise<T> {
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
    upload<Lecture>(`/lectures/${id}/audio`, file, filename, onProgress),
  transcribe: (id: number) => request<Job>(`/lectures/${id}/transcribe`, { method: 'POST' }),
  jobs: (id: number) => request<LectureJobs>(`/lectures/${id}/jobs`),
  transcript: (id: number) => request<Transcript>(`/lectures/${id}/transcript`),

  listNotes: (lectureId: number) => request<Note[]>(`/lectures/${lectureId}/notes`),
  generateNotes: (lectureId: number, provider = '', model = '') =>
    request<Job>(`/lectures/${lectureId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ provider, model }),
    }),
  updateNote: (id: number, content_md: string) =>
    request<Note>(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify({ content_md }) }),
  deleteNote: (id: number) => request<void>(`/notes/${id}`, { method: 'DELETE' }),

  listSlides: (lectureId: number) => request<SlideDeck[]>(`/lectures/${lectureId}/slides`),
  uploadSlides: (
    lectureId: number,
    file: Blob,
    filename: string,
    onProgress?: (f: number) => void,
  ) => upload<SlideDeck>(`/lectures/${lectureId}/slides`, file, filename, onProgress),
  deleteSlideDeck: (id: number) => request<void>(`/slides/${id}`, { method: 'DELETE' }),
  slidePdfUrl: (id: number) => `/api/slides/${id}/file`,
  slideTextUrl: (id: number) => `/api/slides/${id}/text`,

  taskProviders: (task: string) => request<ProviderOption[]>(`/tasks/${task}/providers`),

  audioUrl: (id: number) => `/api/lectures/${id}/audio`,
  transcriptTextUrl: (id: number, timestamps: boolean) =>
    `/api/lectures/${id}/transcript.txt?timestamps=${timestamps}`,
}
