// Thin API client. The base URL is baked in at build time by Vite.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

export type Health = { status: string; app: string; env: string; version: string }

export type Readiness = {
  status: 'ready' | 'degraded'
  checks: Record<string, { status: string; detail?: string; queue_depth?: number }>
}

export type AgentProfile = {
  id: string
  name: string
  role: string
  system_prompt: string
  allowed_tools_json: string[]
  approval_rules_json: { auto_approved?: string[]; requires_approval?: string[] }
  created_at: string
  updated_at: string
}

export type SystemSummary = {
  phase: number
  phase_name: string
  app: string
  env: string
  agent_runtime: string
  counts: Record<string, number>
}

export type Topic = {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

export type TopicDetail = Topic & {
  source_count: number
  memory_count: number
  chunk_count: number
  project_count: number
  memory_types: Record<string, number>
}

export type SourceStatus = 'registered' | 'ingesting' | 'ingested' | 'failed'

export type Source = {
  id: string
  topic_id: string
  type: string
  name: string
  uri: string | null
  status: SourceStatus
  metadata_json: Record<string, unknown> & { last_ingestion?: IngestionSummary }
  created_at: string
  updated_at: string
}

export type IngestionSummary = {
  status: string
  documents: number
  chunks_created: number
  chunks_skipped_duplicate: number
  memories_created: number
  memories_skipped_duplicate: number
  memory_types: Record<string, number>
  embedding_provider: string
  memory_extractor: string
  error: string | null
  notes: string[]
}

export type Memory = {
  id: string
  topic_id: string
  project_id: string | null
  source_id: string | null
  type: string
  content: string
  confidence: number
  importance: number
  metadata_json: Record<string, unknown>
  created_at: string
}

export type MemorySearchHit = {
  memory: Memory
  score: number
  similarity: number
  components: Record<string, number>
}

export type MemorySearchResponse = {
  query: string
  count: number
  weights: Record<string, number>
  results: MemorySearchHit[]
}

export const MEMORY_TYPES = [
  'fact',
  'decision',
  'constraint',
  'risk',
  'architecture',
  'definition',
  'person',
  'system',
  'open_question',
  'lesson',
  'gotcha',
] as const

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

type RequestOptions = { method?: string; body?: unknown; okStatuses?: number[] }

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, okStatuses = [] } = options
  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const payload = await response.json().catch(() => null)

  if (!response.ok && !okStatuses.includes(response.status)) {
    // FastAPI puts the useful message in `detail`.
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : null
    throw new ApiError(
      typeof detail === 'string' ? detail : `${response.status} ${response.statusText}`,
      response.status,
    )
  }
  return payload as T
}

export type NewSource = {
  type: string
  name: string
  uri?: string
  text?: string
}

export const api = {
  baseUrl: BASE_URL,
  health: () => request<Health>('/health'),
  // Readiness answers 503 with a useful body; treat that as data, not failure.
  readiness: () => request<Readiness>('/health/ready', { okStatuses: [503] }),
  agentProfiles: () => request<AgentProfile[]>('/agent-profiles'),
  systemSummary: () => request<SystemSummary>('/system/summary'),

  topics: () => request<Topic[]>('/topics'),
  topic: (id: string) => request<TopicDetail>(`/topics/${id}`),
  createTopic: (name: string, description?: string) =>
    request<Topic>('/topics', { method: 'POST', body: { name, description: description || null } }),

  sources: (topicId: string) => request<Source[]>(`/topics/${topicId}/sources`),
  createSource: (topicId: string, source: NewSource) =>
    request<Source>(`/topics/${topicId}/sources`, { method: 'POST', body: source }),
  ingestSource: (sourceId: string, mode: 'async' | 'sync' = 'async') =>
    request<{ mode: string; summary?: IngestionSummary; job_id?: string }>(
      `/sources/${sourceId}/ingest?mode=${mode}`,
      { method: 'POST', okStatuses: [202, 422] },
    ),

  memories: (topicId: string, type?: string) =>
    request<Memory[]>(`/topics/${topicId}/memories${type ? `?type=${type}` : ''}`),
  searchMemory: (query: string, topicId?: string, types?: string[]) =>
    request<MemorySearchResponse>('/memory/search', {
      method: 'POST',
      body: { query, topic_id: topicId ?? null, types: types?.length ? types : null, limit: 20 },
    }),
}
