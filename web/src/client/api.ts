// Phase 24 §6: centralizes the Bearer header, typed responses, and an
// error taxonomy — 401 means re-auth, 403 means a real governance deny
// (shown verbatim, never swallowed), anything else surfaces the real
// backend message rather than a generic "something went wrong".

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function getToken(): string | null {
  return localStorage.getItem('control_ui_token')
}

export function setToken(token: string) {
  localStorage.setItem('control_ui_token', token)
}

export function clearToken() {
  localStorage.removeItem('control_ui_token')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(path, { ...init, headers })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = body.detail || body.reason || JSON.stringify(body)
    } catch {
      // response body wasn't JSON — fall back to statusText above
    }
    if (resp.status === 401) clearToken()
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return resp.json()
}

export interface Task {
  id: string
  title: string
  description: string
  status: string
  priority: string
  requested_by: string
  correlation_id: string
  conversation_id: string | null
  created_at: string
  updated_at: string
}

export interface TaskEvent {
  id: string
  task_id: string
  from_status: string | null
  to_status: string
  actor: string
  detail: string
  ts: string
}

export interface Conversation {
  id: string
  title: string
  created_by: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface Approval {
  id: string
  action: string
  requested_by: string
  risk_tier: string
  created_at: string
  expires_at: string | null
}

export interface Bootstrap {
  actor: string
  services: Record<string, boolean>
  capability_views: unknown[]
}

// --- Gateway (direct — chat submits tasks through the real governed path) ---

export function createTask(body: { title: string; description?: string; conversation_id?: string }): Promise<Task> {
  return request('/api/v1/tasks', { method: 'POST', body: JSON.stringify(body) })
}

export function getTask(taskId: string): Promise<Task> {
  return request(`/api/v1/tasks/${taskId}`)
}

// --- control-ui BFF ---

export function getBootstrap(): Promise<Bootstrap> {
  return request('/ui/bootstrap')
}

export function listConversations(): Promise<Conversation[]> {
  return request('/ui/conversations')
}

export function createConversation(title: string): Promise<Conversation> {
  return request('/ui/conversations', { method: 'POST', body: JSON.stringify({ title }) })
}

export function getTimeline(conversationId: string): Promise<{ turns: { task: Task; events: TaskEvent[] }[]; partial: boolean }> {
  return request(`/ui/conversations/${conversationId}/timeline`)
}

export function getApprovalsInbox(): Promise<Approval[]> {
  return request('/ui/approvals/inbox')
}

export function decideApproval(id: string, approve: boolean, comment: string): Promise<{ id: string; status: string }> {
  return request(`/ui/approvals/${id}/decide`, { method: 'POST', body: JSON.stringify({ approve, comment }) })
}

// --- Observability (direct, read-only — Phase 24 §5.3: "consumes Phase 13 unchanged") ---

export function getMetricsOverview(): Promise<Record<string, unknown>> {
  return request('/metrics/overview')
}

export function getHealthSystem(): Promise<Record<string, unknown>> {
  return request('/health/system')
}

export { getToken }
