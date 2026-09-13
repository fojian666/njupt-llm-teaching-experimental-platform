/** 与后端模型对齐的类型定义。字段名保持 snake_case，省掉一层映射。 */

export interface UserInfo {
  id: number
  username: string
  name: string
  role: 'admin' | 'teacher' | 'student'
  role_label: string
  is_manager: boolean
  email: string
}

// ---------------- 数据管理 ----------------
export interface Category {
  id: number
  name: string
  code: string
  parent_id: number | null
  sort: number
  remark: string
  full_path: string
  resource_count: number
  children: Category[]
}

export interface DataTag {
  id: number
  name: string
  color: string
  resource_count: number
}

export interface DataResource {
  id: number
  name: string
  category_id: number | null
  category_path: string
  upload_method: string
  upload_method_label: string
  file_format: string
  file_size: number
  file_size_label: string
  tags: string[]
  parse_status: string
  parse_status_label: string
  parse_message: string
  char_count: number
  content_preview?: string
  source_note: string
  created_at: string
  updated_at: string
  in_knowledge_bases: string[]
}

// ---------------- 知识管理 ----------------
export interface KnowledgeBase {
  id: number
  name: string
  code: string
  description: string
  embedding_model_id: number | null
  embedding_model_name: string
  chunk_size: number
  chunk_overlap: number
  chunk_strategy: string
  is_active: boolean
  doc_count: number
  chunk_count: number
  created_at: string
  warning?: string
}

export interface KnowledgeDoc {
  id: number
  knowledge_base_id: number
  resource_id: number
  name: string
  file_format: string
  category_path: string
  tags: string[]
  parse_status: string
  parse_status_label: string
  parse_message: string
  is_active: boolean
  chunk_count: number
  char_count: number
  parsed_at: string | null
  created_at: string
}

export interface Chunk {
  id: number
  seq: number
  chapter_path: string
  content: string
  char_count: number
  has_embedding: boolean
}

export interface Citation {
  index: number
  chunk_id: number
  doc_id: number
  source_name: string
  chapter_path: string
  content?: string
  snippet: string
  score: number
  vector_score: number
  lexical_score: number
  cited?: boolean
}

// ---------------- 智能体 ----------------
export interface Agent {
  id: number
  name: string
  code: string
  avatar: string
  description: string
  welcome_message: string
  suggested_questions: string[]
  system_prompt: string
  model_id: number | null
  model_name: string
  knowledge_base_ids: number[]
  knowledge_base_names: string[]
  top_k: number
  score_threshold: number
  temperature: number
  retrieval_first: boolean
  status: string
  status_label: string
  conversation_count: number
  created_at: string
}

export interface Conversation {
  id: number
  agent_id: number
  agent_name: string
  title: string
  model_name: string
  knowledge_base_names: string[]
  message_count: number
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  reasoning?: string
  citations?: Citation[]
  /** 本次回答的检索过程，仅前端内存保留（后端未持久化），用于展示可解释性 */
  retrieval?: RetrievalMeta
  model_name?: string
  latency_ms?: number
  is_error?: boolean
  feedback?: string | null
  created_at?: string
}

export interface RetrievalMeta {
  /** 向量召回候选条数 */
  vector: number
  /** 关键词召回候选条数 */
  lexical: number
  /** 融合后进入提示词的条数 */
  fused: number
  /** 本次是否启用了关键词召回 */
  useKeyword: boolean
}

// ---------------- 配置中心 ----------------
export interface ModelProvider {
  id: number
  name: string
  code: string
  base_url: string
  has_key: boolean
  key_hint: string
  is_active: boolean
  sort: number
  remark: string
  model_count: number
}

export interface ModelConfig {
  id: number
  provider_id: number
  provider_name: string
  name: string
  model_id: string
  kind: 'llm' | 'embedding' | 'rerank'
  kind_label: string
  dimension: number | null
  max_tokens: number
  temperature: number
  is_default: boolean
  is_active: boolean
  sort: number
}

export interface LlmOption {
  id: number
  name: string
  model_id: string
  provider: string
  is_default: boolean
}

// ---------------- 问答记录 ----------------
export interface QARecord {
  id: number
  conversation_id: number
  conversation_title: string
  agent_id: number
  agent_name: string
  user_name: string
  question: string
  answer: string
  citation_count: number
  cited_count: number
  citations: Citation[]
  model_name: string
  latency_ms: number
  is_error: boolean
  feedback: string | null
  created_at: string
}

export interface OperationLog {
  id: number
  user_name: string
  action: string
  target_type: string
  target_id: string
  detail: Record<string, unknown>
  ip: string | null
  created_at: string
}
