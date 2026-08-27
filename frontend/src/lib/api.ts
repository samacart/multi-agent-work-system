// Thin API client. The base URL is baked in at build time by Vite.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

export type Health = {
  status: string
  app: string
  env: string
  version: string
}

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

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`)
  // Readiness answers 503 with a useful body; treat that as data, not failure.
  if (!response.ok && response.status !== 503) {
    throw new Error(`${response.status} ${response.statusText} for ${path}`)
  }
  return (await response.json()) as T
}

export const api = {
  baseUrl: BASE_URL,
  health: () => request<Health>('/health'),
  readiness: () => request<Readiness>('/health/ready'),
  agentProfiles: () => request<AgentProfile[]>('/agent-profiles'),
  systemSummary: () => request<SystemSummary>('/system/summary'),
}
