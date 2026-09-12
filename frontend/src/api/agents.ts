import { http, getList } from './http'
import type { Agent, Conversation, ChatMessage, QARecord, OperationLog } from '@/types'

export const agentApi = {
  list: (params?: Record<string, unknown>) => getList<Agent>('/agents/', params),
  /** 智能体广场：只列已发布的 */
  square: (keyword = '') => http.get<{ items: Agent[] }>('/agents/square', { params: { keyword } }).then((r) => r.data),
  get: (id: number) => http.get<Agent>(`/agents/${id}`).then((r) => r.data),
  create: (payload: Record<string, unknown>) => http.post<Agent>('/agents/', payload).then((r) => r.data),
  update: (id: number, payload: Record<string, unknown>) => http.patch(`/agents/${id}`, payload),
  publish: (id: number, status = 'published') => http.post(`/agents/${id}/publish?status=${status}`),
  remove: (id: number) => http.delete(`/agents/${id}`),

  conversations: (agentId: number) => http.get<Conversation[]>(`/agents/${agentId}/conversations`).then((r) => r.data),
  createConversation: (agentId: number) =>
    http.post<Conversation>(`/agents/${agentId}/conversations`).then((r) => r.data),
  renameConversation: (id: number, title: string) => http.patch(`/agents/conversations/${id}`, null, { params: { title } }),
  removeConversation: (id: number) => http.delete(`/agents/conversations/${id}`),
  messages: (conversationId: number) => http.get<ChatMessage[]>(`/agents/conversations/${conversationId}/messages`).then((r) => r.data),
  feedback: (messageId: number, rating: 'like' | 'dislike', comment = '') =>
    http.post(`/agents/messages/${messageId}/feedback`, { rating, comment }),
}

export const auditApi = {
  records: (params?: Record<string, unknown>) => getList<QARecord>('/audit/records', params),
  logs: (params?: Record<string, unknown>) => getList<OperationLog>('/audit/logs', params),
  logActions: () => http.get('/audit/logs/actions').then((r) => r.data),
  stats: (days = 7) => http.get('/audit/stats', { params: { days } }).then((r) => r.data),
}
