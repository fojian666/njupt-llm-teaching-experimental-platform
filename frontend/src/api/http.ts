import axios from 'axios'
import { ElMessage } from 'element-plus'

/**
 * 统一的请求封装。
 *
 * 后端用 session 鉴权，Vite 把 /api 代理到 Django，所以这里不需要带 token，
 * `withCredentials` 也不是必须的 —— 但开着无害，部署到反代后面时不用改代码。
 */
export const http = axios.create({
  baseURL: '/api',
  timeout: 120_000,
  withCredentials: true,
})

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail || error.response?.data?.message
    if (status === 401) {
      // 会话失效：跳登录页。用 location 而不是 router，避免在拦截器里循环依赖
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login'
      }
    } else if (detail) {
      ElMessage.error(String(detail))
    } else if (error.message) {
      ElMessage.error(`请求失败：${error.message}`)
    }
    return Promise.reject(error)
  },
)

/** 分页响应的统一形状（与后端 apps/common/api.py#paginate 对齐） */
export interface Page<T> {
  total: number
  page: number
  page_size: number
  pages: number
  items: T[]
}

export async function getList<T>(url: string, params?: Record<string, unknown>): Promise<Page<T>> {
  const { data } = await http.get<Page<T>>(url, { params })
  return data
}
