import { http } from './http'
import type { UserInfo, LlmOption } from '@/types'

export const authApi = {
  async login(username: string, password: string): Promise<UserInfo> {
    const { data } = await http.post<UserInfo>('/auth/login', { username, password })
    return data
  },
  async logout(): Promise<void> {
    await http.post('/auth/logout')
  },
  async me(): Promise<UserInfo> {
    const { data } = await http.get<UserInfo>('/auth/me')
    return data
  },
}

export const configApi = {
  /** 对话页的模型下拉。后端没配模型时会退回环境变量默认值 */
  async llmOptions(): Promise<{ items: LlmOption[]; default_id: number }> {
    const { data } = await http.get('/configs/llm-options')
    return data
  },
}
