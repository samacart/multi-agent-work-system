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

export type AttentionItem = {
  kind:
    | 'degraded_dependency'
    | 'approval'
    | 'failed_run'
    | 'stale_run'
    | 'blocked_task'
    | 'open_question'
    | 'config_warning'
    | string
  title: string
  why: string
  project_id: string | null
  project_name: string | null
  blast_radius: number
  risk: 'low' | 'medium' | 'high' | string
  age_seconds: number
  link: string
  action_id: string | null
  score: number
  components: Record<string, number>
}

export type Attention = {
  count: number
  needs_you: boolean
  weights: Record<string, unknown>
  items: AttentionItem[]
}

export type SystemSummary = {
  phase: number
  phase_name: string
  app: string
  env: string
  agent_runtime: string
  available_runtimes: string[]
  embedding_provider: string
  memory_extractor: string
  github_enabled: boolean
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


export type ProjectStatus =
  | 'draft'
  | 'planning'
  | 'ready'
  | 'running'
  | 'blocked'
  | 'review'
  | 'delivered'
  | 'archived'

export type Project = {
  id: string
  topic_id: string | null
  name: string
  goal: string | null
  status: ProjectStatus
  brief: string | null
  workspace_path: string | null
  created_at: string
  updated_at: string
}

export type WorkspaceValidation = {
  path: string
  valid: boolean
  reason: string | null
  resolved_path: string | null
  branch: string | null
  dirty_files: number
  is_agent_branch: boolean
  warnings: string[]
}

export type WorkspaceStatus = {
  project_workspace: string | null
  resolved_workspace: string | null
  using_global_fallback: boolean
  validation: WorkspaceValidation
}

export type ProjectDetail = Project & {
  resolved_workspace: string | null
  topic_name: string | null
  task_counts: Record<string, number>
  run_count: number
  artifact_count: number
  open_questions: number
  pending_approvals: number
}

export const TASK_STATUSES = [
  'backlog',
  'ready',
  'in_progress',
  'blocked',
  'review',
  'verified',
  'done',
] as const

export type TaskStatus = (typeof TASK_STATUSES)[number]

export type Task = {
  id: string
  project_id: string
  parent_task_id: string | null
  title: string
  description: string | null
  agent_role: string | null
  status: TaskStatus
  acceptance_criteria: string[]
  evidence: EvidenceEntry[]
  metadata_json: {
    depends_on?: string[]
    blocked_reason?: string
    dropped_from_plan?: string
  } & Record<string, unknown>
  created_at: string
  updated_at: string
}

export type EvidenceEntry = {
  criterion: string
  verdict: 'met' | 'not_met' | 'unverified' | string
  evidence: string
  attributed_to?: string
  rationale?: string | null
}

export type Criterion = {
  task_id: string
  task_title: string
  task_status: string
  agent_role: string | null
  criterion: string
  verdict: string
  evidence: string
  attributed_to: string | null
  rationale: string | null
}

export type Blockers = {
  task_id: string
  status: string
  reason: string | null
  approvals: Approval[]
  dependencies: string[]
  failed_run_id: string | null
  unmet_criteria: string[]
}

export type AgentRun = {
  id: string
  project_id: string | null
  task_id: string | null
  agent_profile_id: string
  status: string
  input: { task?: string; instruction?: string; runtime?: string }
  output: Record<string, unknown> | null
  error: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export type Artifact = {
  id: string
  project_id: string
  task_id: string | null
  type: string
  title: string
  content: string
  path: string | null
  created_at: string
}

export type ApprovalBriefing = {
  summary: string
  recommendation: 'approve' | 'approve_with_changes' | 'revise' | string
  rationale: string
  key_points: string[]
  concerns: string[]
  contradicts_earlier_stage: string[]
}

export type Approval = {
  id: string
  project_id: string | null
  task_id: string | null
  action_type: string
  action_summary: string
  risk_level: 'low' | 'medium' | 'high'
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  response: string | null
  metadata_json: { briefing?: ApprovalBriefing; reviewed_by?: string; briefing_error?: string }
  created_at: string
  updated_at: string
}

/**
 * Stage gates ask you to approve one specific artifact. Being asked to approve
 * something you cannot see is not a decision, it is a rubber stamp.
 */
export const APPROVAL_ARTIFACT: Record<string, string> = {
  approve_project_brief: 'project_brief',
  approve_architecture_plan: 'architecture_plan',
  approve_task_breakdown: 'task_breakdown',
}

/** Roles the SDLC loop refuses to run while any approval is pending. */
export const GATED_ROLES = ['developer', 'architect', 'release_manager']

export type Decision = {
  id: string
  project_id: string
  question: string
  answer: string | null
  rationale: string | null
  decided_by: string | null
  metadata_json: { options?: string[]; recommendation?: string | null }
  created_at: string
}

export type GitHubStatus = {
  enabled: boolean
  authenticated: boolean
  writes_enabled: boolean
  api_url: string
  supported_source_types: string[]
}

export type SdlcResult = {
  project_id: string
  status: string
  tasks_run: number
  tasks_verified: number
  tasks_done: number
  tasks_blocked: number
  tasks_skipped: number
  runs: string[]
  artifacts: string[]
  findings: number
  blocking_findings: number
  lessons_stored: number
  notes: string[]
  error: string | null
}

export type PlanningResult = {
  project_id: string
  status: string
  memories_used: number
  runs: string[]
  tasks_created: number
  tasks_updated: number
  questions_created: number
  approvals_created: number
  artifacts: string[]
  error: string | null
}

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
  attention: () => request<Attention>('/attention'),

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

  projects: () => request<Project[]>('/projects'),
  project: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (name: string, goal?: string, topicId?: string, workspacePath?: string) =>
    request<Project>('/projects', {
      method: 'POST',
      body: {
        name,
        goal: goal || null,
        topic_id: topicId || null,
        workspace_path: workspacePath || null,
      },
    }),
  setWorkspace: (projectId: string, workspacePath: string) =>
    request<Project>(`/projects/${projectId}`, {
      method: 'PATCH',
      body: { workspace_path: workspacePath },
    }),
  workspace: (projectId: string) => request<WorkspaceStatus>(`/projects/${projectId}/workspace`),
  planProject: (id: string) =>
    request<PlanningResult>(`/projects/${id}/plan`, { method: 'POST', okStatuses: [422] }),
  runProject: (id: string) => request<SdlcResult>(`/projects/${id}/run`, { method: 'POST' }),

  githubStatus: () => request<GitHubStatus>('/github/status'),
  branch: (projectId: string) => request<{ branch: string }>(`/projects/${projectId}/branch`),
  prDescription: (projectId: string, base = 'main') =>
    request<{ title: string; branch: string; base: string; content: string }>(
      `/projects/${projectId}/pr-description`,
      { method: 'POST', body: { base } },
    ),

  tasks: (projectId: string) => request<Task[]>(`/projects/${projectId}/tasks`),
  updateTask: (taskId: string, patch: Partial<Pick<Task, 'status' | 'title' | 'description'>>) =>
    request<Task>(`/tasks/${taskId}`, { method: 'PATCH', body: patch }),
  criteria: (projectId: string, verdict?: string) =>
    request<Criterion[]>(`/projects/${projectId}/criteria${verdict ? `?verdict=${verdict}` : ''}`),
  attachEvidence: (taskId: string, entry: EvidenceEntry) =>
    request<Task>(`/tasks/${taskId}/evidence`, { method: 'PATCH', body: entry }),
  blockers: (taskId: string) => request<Blockers>(`/tasks/${taskId}/blockers`),
  transitions: () => request<Record<string, string[]>>('/tasks/transitions'),

  runs: (projectId: string) => request<AgentRun[]>(`/projects/${projectId}/runs`),
  artifacts: (projectId: string) => request<Artifact[]>(`/projects/${projectId}/artifacts`),

  approvals: (projectId: string) => request<Approval[]>(`/projects/${projectId}/approvals`),
  respondToApproval: (approvalId: string, status: string, response?: string) =>
    request<Approval>(`/approvals/${approvalId}/respond`, {
      method: 'POST',
      body: { status, response: response || null },
    }),

  decisions: (projectId: string) => request<Decision[]>(`/projects/${projectId}/decisions`),
  answerDecision: (decisionId: string, answer: string, rationale?: string) =>
    request<Decision>(`/decisions/${decisionId}/answer`, {
      method: 'POST',
      body: { answer, rationale: rationale || null, decided_by: 'human' },
    }),
}
