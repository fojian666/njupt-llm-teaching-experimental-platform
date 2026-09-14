import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
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

/**
 * 调用方想自己处理错误（比如"删不掉就只刷新列表"）时传 silent: true，
 * 拦截器就不再弹全局提示。显式的选项比散落的空 catch 好读，也好搜。
 */
export interface RequestOptions extends AxiosRequestConfig {
  silent?: boolean
}

// --------------------------------------------------------------------------
// 错误文案：把后端的结构翻译成人话
// --------------------------------------------------------------------------
/** pydantic 的约束名 → 中文说法。字段校验失败时后端回的是英文 msg。 */
const CONSTRAINT_TEXT: [RegExp, string][] = [
  [/at least (\d+) character/i, '不能为空'],
  [/at most (\d+) character/i, '超出长度限制'],
  [/string too short/i, '内容太短'],
  [/string too long/i, '内容太长'],
  [/field required/i, '必填项缺失'],
  [/input should be a valid integer/i, '需要填数字'],
  [/input should be a valid boolean/i, '需要是开关值'],
  [/input should be a valid number/i, '需要填数字'],
  [/not a valid (integer|float)/i, '格式不正确'],
]

function humanizeFieldMessage(msg: string): string {
  for (const [re, text] of CONSTRAINT_TEXT) {
    if (re.test(msg)) return text
  }
  return msg
}

/** 常见字段名 → 中文，避免提示里直接出现 name / ids 这类标识符 */
const FIELD_TEXT: Record<string, string> = {
  name: '名称',
  code: '标识',
  base_url: '接口地址',
  model_id: '模型 ID',
  provider_id: '供应商',
  dimension: '向量维度',
  question: '问题',
  content: '内容',
  chapter_path: '章节路径',
  ids: '选中的条目',
  category_id: '目标分类',
  tags: '标签',
  rating: '评价',
  score_threshold: '分数门槛',
  top_k: '检索条数',
}

function humanizeFieldName(field: string): string {
  return FIELD_TEXT[field] ?? field
}

/** 后端 422 回的是 [{loc: [...], msg: ...}]，直接 String() 会变成 [object Object] */
function formatValidationDetail(detail: unknown): string {
  if (!Array.isArray(detail)) return ''
  const parts = detail.slice(0, 4).map((item) => {
    const loc = Array.isArray((item as { loc?: unknown[] })?.loc) ? (item as { loc: unknown[] }).loc : []
    const msg = String((item as { msg?: unknown })?.msg ?? '')
    // loc 形如 ["body", "payload", "name"]，最后一段才是字段名
    const field = loc.length ? String(loc[loc.length - 1]) : ''
    const text = humanizeFieldMessage(msg)
    return !field || field === 'body' ? text : `${humanizeFieldName(field)}：${text}`
  })
  const rest = detail.length > 4 ? ` 等 ${detail.length} 项` : ''
  return parts.join('；') + rest
}

function resolveMessage(error: AxiosError): { text: string; level: 'error' | 'warning' } {
  const status = error.response?.status
  const data = error.response?.data as { detail?: unknown; message?: string } | undefined
  const detail = data?.detail
  const plain = typeof detail === 'string' ? detail : data?.message || ''

  if (status === 422) {
    const formatted = formatValidationDetail(detail)
    return { text: formatted ? `填写有误 —— ${formatted}` : '提交的内容不符合要求', level: 'warning' }
  }
  if (status === 429) {
    // 限流是「稍后再试」，不是错误，用 warning 语气
    return { text: plain || '操作过于频繁，请稍后再试', level: 'warning' }
  }
  if (status === 403) return { text: plain || '当前账号没有该操作权限', level: 'warning' }
  if (status && status >= 500) {
    return { text: plain || `服务出错了（${status}），请稍后重试`, level: 'error' }
  }
  if (!error.response) {
    if (error.code === 'ECONNABORTED' || /timeout/i.test(error.message)) {
      return { text: '请求超时，可能是网络慢或文件较大，请重试', level: 'error' }
    }
    return { text: '网络不可用，请检查连接后重试', level: 'error' }
  }
  return { text: plain || `请求失败（${status}）`, level: 'error' }
}

// --------------------------------------------------------------------------
// 全局提示去重：一批并发请求同时失败时，不该刷出一排一模一样的提示
// --------------------------------------------------------------------------
let lastToast = ''
let lastToastAt = 0

function toastOnce(text: string, level: 'error' | 'warning') {
  const now = Date.now()
  if (text === lastToast && now - lastToastAt < 1500) return
  lastToast = text
  lastToastAt = now
  ElMessage({ message: text, type: level, duration: level === 'warning' ? 2600 : 3200 })
}

http.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError) => {
    const config = error.config as RequestOptions | undefined
    const status = error.response?.status

    if (status === 401) {
      // 会话失效：跳登录页。用 location 而不是 router，避免在拦截器里循环依赖
      if (!location.pathname.startsWith('/login')) {
        location.href = '/login'
      }
      return Promise.reject(error)
    }
    if (!config?.silent) {
      const { text, level } = resolveMessage(error)
      toastOnce(text, level)
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
