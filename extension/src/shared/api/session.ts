import { apiRequest } from './client'

export interface Session {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  audio_url?: string
  created_at: string
}

export interface SessionDetail extends Session {
  messages: Message[]
}

export async function listSessions(): Promise<Session[]> {
  // 后端返回 {sessions: Session[]}
  const resp = await apiRequest<{ sessions: Session[] } | Session[]>('/api/sessions', {
    method: 'GET',
  })
  return Array.isArray(resp) ? resp : resp.sessions || []
}

export async function createSession(title = '新对话'): Promise<Session> {
  return await apiRequest<Session>('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export async function deleteSession(id: number): Promise<void> {
  await apiRequest(`/api/sessions/${id}`, { method: 'DELETE', parseJson: false })
}

export async function renameSession(id: number, title: string): Promise<Session> {
  return await apiRequest<Session>(`/api/sessions/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  })
}

/** 获取会话详情（含消息）。后端路径为 /api/sessions/{id} */
export async function getSessionDetail(sessionId: number): Promise<SessionDetail> {
  return await apiRequest<SessionDetail>(`/api/sessions/${sessionId}`, { method: 'GET' })
}

/** 兼容旧调用：只取消息列表 */
export async function getMessages(sessionId: number): Promise<Message[]> {
  const detail = await getSessionDetail(sessionId)
  return detail.messages || []
}
