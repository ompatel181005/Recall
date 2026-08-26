// Typed fetch client for the TranscribeAI backend (/api is proxied by Vite in dev).

export interface Health {
  status: string
  providers: Record<string, boolean> // claude / openai / ollama -> usable now
  cuda: boolean
  tasks: Record<string, { provider: string; model: string }>
  transcription_model: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/health'),
  // M1: courses/lectures CRUD, audio upload, transcript fetch
}
