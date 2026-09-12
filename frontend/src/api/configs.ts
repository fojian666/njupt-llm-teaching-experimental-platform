import { http } from './http'
import type { ModelProvider, ModelConfig } from '@/types'

/** 配置中心：供应商 / 模型管理。写操作后端要求管理员或教师角色。 */
export const providerApi = {
  list: () => http.get<ModelProvider[]>('/configs/providers').then((r) => r.data),
  create: (payload: Record<string, unknown>) => http.post<ModelProvider>('/configs/providers', payload),
  update: (id: number, payload: Record<string, unknown>) => http.patch<ModelProvider>(`/configs/providers/${id}`, payload),
  remove: (id: number) => http.delete(`/configs/providers/${id}`),
}

export const modelApi = {
  list: (kind = '') => http.get<ModelConfig[]>('/configs/models', { params: { kind } }).then((r) => r.data),
  create: (payload: Record<string, unknown>) => http.post<ModelConfig>('/configs/models', payload),
  /** 后端 PATCH 用完整的 ModelIn 结构，这里的 payload 由调用方拼好 */
  update: (id: number, payload: Record<string, unknown>) => http.patch<ModelConfig>(`/configs/models/${id}`, payload),
  remove: (id: number) => http.delete(`/configs/models/${id}`),
}

/** 模型体检：LLM / 向量模型是否可用、来源是配置中心还是环境变量 */
export const statusApi = {
  status: () => http.get('/configs/status').then((r) => r.data),
}
