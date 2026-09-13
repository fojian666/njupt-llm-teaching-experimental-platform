import { http, getList } from './http'
import type { Category, DataResource, DataTag, KnowledgeBase, KnowledgeDoc, Chunk, Citation } from '@/types'

// ---------------- 数据分类管理 ----------------
export const categoryApi = {
  tree: () => http.get<Category[]>('/datasets/categories').then((r) => r.data),
  create: (payload: Partial<Category>) => http.post('/datasets/categories', payload),
  update: (id: number, payload: Partial<Category>) => http.patch(`/datasets/categories/${id}`, payload),
  remove: (id: number) => http.delete(`/datasets/categories/${id}`),
}

export const tagApi = {
  list: () => http.get<DataTag[]>('/datasets/tags').then((r) => r.data),
  remove: (id: number) => http.delete(`/datasets/tags/${id}`),
}

export const resourceApi = {
  list: (params: Record<string, unknown>) => getList<DataResource>('/datasets/resources', params),
  get: (id: number) => http.get(`/datasets/resources/${id}`).then((r) => r.data),
  update: (id: number, payload: Record<string, unknown>) => http.patch(`/datasets/resources/${id}`, payload),
  remove: (id: number) => http.delete(`/datasets/resources/${id}`),
  batchRemove: (ids: number[]) => http.post('/datasets/resources/batch-delete', { ids }),
  /** 解析源文件（只解析，不建向量库）。后端是异步执行，前端轮询状态 */
  parse: (id: number) => http.post(`/datasets/resources/${id}/parse`),
  batchParse: (ids: number[]) => http.post('/datasets/resources/batch-parse', { ids }),
  /** 批量添加标签：增量，不清除已有标签 */
  batchTags: (ids: number[], tags: string[]) => http.post('/datasets/resources/batch-tags', { ids, tags }),
  /** 批量移动到目标分类；categoryId 传 0 表示移出分类 */
  batchMove: (ids: number[], categoryId: number) =>
    http.post('/datasets/resources/batch-move', { ids, category_id: categoryId }),
  /** 源文件下载地址（走 <a href> 直接触发浏览器下载） */
  downloadUrl: (id: number) => `/api/datasets/resources/${id}/download`,
  stats: () => http.get('/datasets/stats').then((r) => r.data),
  formats: () => http.get('/datasets/formats').then((r) => r.data),

  /** 上传文件。tags 用逗号分隔的字符串 —— multipart 里传数组写法太分裂 */
  upload(file: File, extra: { name?: string; category_id?: number; tags?: string; source_note?: string }) {
    const form = new FormData()
    form.append('file', file)
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== null && v !== '') form.append(k, String(v))
    }
    return http.post('/datasets/resources/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600_000, // 大文件上传，别让默认 120s 卡死
    })
  },
}

// ---------------- 知识管理 ----------------
export const kbApi = {
  list: () => http.get<KnowledgeBase[]>('/knowledge/bases').then((r) => r.data),
  create: (payload: Record<string, unknown>) => http.post('/knowledge/bases', payload),
  update: (id: number, payload: Record<string, unknown>) => http.patch(`/knowledge/bases/${id}`, payload),
  remove: (id: number) => http.delete(`/knowledge/bases/${id}`),

  docs: (kbId: number, params?: Record<string, unknown>) => getList<KnowledgeDoc>(`/knowledge/bases/${kbId}/docs`, params),
  /** 把「数据管理」里的数据导入知识库并开始解析 */
  importResources: (kbId: number, resource_ids: number[]) =>
    http.post(`/knowledge/bases/${kbId}/import`, { resource_ids }),
  reparse: (docId: number, reindex = true) => http.post(`/knowledge/docs/${docId}/reparse?reindex=${reindex}`),
  embed: (docId: number) => http.post(`/knowledge/docs/${docId}/embed`),
  toggleDoc: (docId: number) => http.post(`/knowledge/docs/${docId}/toggle`),
  removeDoc: (docId: number) => http.delete(`/knowledge/docs/${docId}`),

  chunks: (docId: number, params?: Record<string, unknown>) => getList<Chunk>(`/knowledge/docs/${docId}/chunks`, params),
  /** 手工添加切片，挂在指定知识条目下 */
  createChunk: (payload: { doc_id: number; content: string; chapter_path?: string }) =>
    http.post('/knowledge/chunks', payload),
  /** 编辑切片正文 / 章节路径 / 有效性；正文变化时后端会现场重新取向量 */
  updateChunk: (id: number, payload: { content?: string; chapter_path?: string; is_active?: boolean }) =>
    http.patch(`/knowledge/chunks/${id}`, payload),
  deleteChunk: (id: number) => http.delete(`/knowledge/chunks/${id}`),
  outline: (docId: number) => http.get(`/knowledge/docs/${docId}/outline`).then((r) => r.data),
  stats: () => http.get('/knowledge/stats').then((r) => r.data),

  /** 检索调试：看向量分 / 关键词分各贡献了多少 */
  search: (payload: { query: string; knowledge_base_ids?: number[]; top_k?: number; alpha?: number; use_keyword?: boolean }) =>
    http.post<{ query: string; vector_count: number; lexical_count: number; note: string; items: Citation[] }>(
      '/knowledge/search',
      payload,
    ).then((r) => r.data),
}
