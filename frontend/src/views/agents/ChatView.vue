<template>
  <div class="chat-wrap">
    <!-- 左侧：会话历史 -->
    <div class="side">
      <el-button type="primary" class="new-btn" @click="newConversation">新建会话</el-button>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === conversationId }"
          @click="openConversation(c.id)"
        >
          <el-icon><ChatDotRound /></el-icon>
          <span class="ctitle">{{ c.title || '新会话' }}</span>
        </div>
        <el-empty v-if="!conversations.length" description="暂无历史" :image-size="60" />
      </div>
    </div>

    <!-- 中间：对话区 -->
    <div class="main">
      <div class="chat-head">
        <div>
          <b>{{ agent?.name || '…' }}</b>
          <span class="muted">{{ agent?.description }}</span>
        </div>
      </div>

      <div class="messages-wrap">
        <div ref="scrollEl" class="messages" @scroll.passive="onScroll">
          <div v-if="!messages.length" class="welcome">
            <h3>{{ agent?.welcome_message }}</h3>
            <div class="sug">
              <el-button v-for="q in agent?.suggested_questions || []" :key="q" size="small" plain @click="ask(q)">
                {{ q }}
              </el-button>
            </div>
          </div>

          <div v-for="(m, i) in messages" :key="m.id ? `m${m.id}` : `t${i}`" class="msg" :class="m.role">
            <div class="bubble">
              <div v-if="m.role === 'assistant' && m.reasoning" class="reasoning">{{ m.reasoning }}</div>
              <div class="md answer-md" :class="{ 'streaming-cursor': i === messages.length - 1 && streaming }" v-html="render(m.content)"></div>
              <div v-if="m.role === 'assistant' && m.model_name && i === messages.length - 1 && !streaming" class="meta">
                {{ m.model_name }}<template v-if="m.latency_ms"> · {{ (m.latency_ms / 1000).toFixed(1) }}s</template>
                <el-button link size="small" @click="rate(m, 'like')"><el-icon><component :is="m.feedback === 'like' ? 'CircleCheckFilled' : 'CircleCheck'" /></el-icon></el-button>
                <el-button link size="small" @click="rate(m, 'dislike')"><el-icon><component :is="m.feedback === 'dislike' ? 'CircleCloseFilled' : 'CircleClose'" /></el-icon></el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- 用户上翻看历史时自动跟滚会让出，给一个回底部的出口 -->
        <transition name="jump">
          <el-button v-if="showJump" class="jump-btn" circle @click="jumpToBottom">
            <el-icon><ArrowDownBold /></el-icon>
          </el-button>
        </transition>
      </div>

      <div v-if="notice" class="notice">{{ notice }}</div>

      <div class="input-area">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          :disabled="streaming"
          placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
          @keydown.enter.exact.prevent="send"
        />
        <div class="opts">
          <el-popover placement="top-start" :width="430" trigger="click">
            <template #reference>
              <el-button size="small">
                <el-icon><Setting /></el-icon>
                <span class="opt-label">{{ currentModelLabel }} · {{ kbIds.length ? `${kbIds.length} 个知识库` : '未选知识库' }} · top_k {{ topK }}</span>
              </el-button>
            </template>
            <div class="param-panel">
              <div class="param-item">
                <div class="param-label">对话模型</div>
                <el-select v-model="modelId" placeholder="默认模型" size="small" clearable style="width: 100%">
                  <el-option v-for="m in llmOptions" :key="m.id" :label="m.name" :value="m.id" />
                </el-select>
              </div>
              <div class="param-item">
                <div class="param-label">知识库（可多选）</div>
                <el-select v-model="kbIds" multiple collapse-tags size="small" style="width: 100%">
                  <el-option v-for="k in kbs" :key="k.id" :label="k.name" :value="k.id" />
                </el-select>
              </div>
              <div class="param-item">
                <div class="param-label">检索条数 top_k：{{ topK }}</div>
                <el-slider v-model="topK" :min="1" :max="20" size="small" />
              </div>
              <div class="param-item param-switches">
                <el-checkbox v-model="retrievalFirst" size="small">检索优先</el-checkbox>
                <el-checkbox v-model="useKeyword" size="small">关键词召回</el-checkbox>
              </div>
            </div>
          </el-popover>
          <el-button v-if="streaming" type="warning" @click="stop">停止生成</el-button>
          <el-button v-else type="primary" :disabled="!input.trim()" @click="send">发送</el-button>
        </div>
      </div>
    </div>

    <!-- 右侧：检索来源 -->
    <div class="side right">
      <div class="cite-head">
        <b>检索来源</b>
        <el-tag size="small" type="info">{{ citations.length }}</el-tag>
      </div>
      <div class="cite-list">
        <div
          v-for="c in citations"
          :key="`${c.chunk_id}-${c.index}`"
          class="citation-item"
          :class="{ 'is-cited': c.cited }"
          :style="{ '--i': Math.min(c.index, 10) }"
        >
          <div class="cite-top">
            <span class="idx">[{{ c.index }}]</span>
            <span class="src">{{ c.source_name }}</span>
          </div>
          <div class="path">{{ c.chapter_path || '（无章节路径）' }}</div>
          <div class="snippet">{{ c.snippet }}</div>
          <div class="scores">
            综合 {{ c.score.toFixed(3) }} · 向量 {{ c.vector_score.toFixed(3) }} · 关键词 {{ c.lexical_score.toFixed(3) }}
            <el-tag v-if="c.cited" size="small" type="success">已引用</el-tag>
          </div>
        </div>
        <el-empty v-if="!citations.length" description="尚未检索" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
// hljs 走 core + 按需注册：整包会把 190+ 种语言一起打进前端（约 1MB）。
// 这里按“物联网/计算机类课程可能出现的代码”挑一组；要加语言就 import + register 一行。
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import cpp from 'highlight.js/lib/languages/cpp'
import c from 'highlight.js/lib/languages/c'
import arduino from 'highlight.js/lib/languages/arduino'
import ini from 'highlight.js/lib/languages/ini'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import matlab from 'highlight.js/lib/languages/matlab'
import python from 'highlight.js/lib/languages/python'
import shell from 'highlight.js/lib/languages/shell'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import 'highlight.js/styles/github-dark.css'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('c', c)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('arduino', arduino)
hljs.registerLanguage('ini', ini)
hljs.registerLanguage('java', java)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('matlab', matlab)
hljs.registerLanguage('python', python)
hljs.registerLanguage('shell', shell)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('yaml', yaml)

import { agentApi } from '@/api/agents'
import { kbApi } from '@/api/datasets'
import { configApi } from '@/api/auth'
import { streamChat } from '@/api/sse'
import type { Agent, ChatMessage, Citation, Conversation, KnowledgeBase, LlmOption } from '@/types'

const route = useRoute()
const agentId = Number(route.params.id)

const escapeHtml = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/**
 * 返回完整的高亮代码块 HTML。
 * markdown-it 看到返回值以 <pre 开头就原样使用、不再自己包一层；
 * 关键是带上 class="hljs" —— github-dark 主题的容器色（深底浅字）挂在 .hljs 上，
 * 只返回内部片段的话主题色对不上，会出现浅色字配浅色底的看不清问题。
 */
const highlight = (code: string, lang: string): string => {
  if (lang && hljs.getLanguage(lang)) {
    try {
      const html = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
      return `<pre class="hljs"><code class="hljs language-${lang}">${html}</code></pre>`
    } catch {
      /* 落到下面的纯文本分支 */
    }
  }
  return `<pre class="hljs"><code class="hljs">${escapeHtml(code)}</code></pre>`
}
const md = new MarkdownIt({
  html: false, // 禁止 HTML —— 模型输出不可信，防注入
  linkify: true,
  highlight,
})

function render(text: string) {
  return md.render(text || '')
}

const agent = ref<Agent | null>(null)
const conversations = ref<Conversation[]>([])
const conversationId = ref<number | null>(null)
const messages = ref<ChatMessage[]>([])
const citations = ref<Citation[]>([])
const notice = ref('')
const input = ref('')
const streaming = ref(false)
const scrollEl = ref<HTMLElement>()

const kbs = ref<KnowledgeBase[]>([])
const kbIds = ref<number[]>([])
const llmOptions = ref<LlmOption[]>([])
const modelId = ref<number | null>(null)
const topK = ref(5)
const currentModelLabel = computed(() => {
  if (modelId.value == null) return '默认模型'
  return llmOptions.value.find((m) => m.id === modelId.value)?.name ?? '自定义模型'
})
const retrievalFirst = ref(true)
const useKeyword = ref(true)

let abort: AbortController | null = null

async function loadAll() {
  agent.value = await agentApi.get(agentId)
  conversations.value = await agentApi.conversations(agentId)
  kbIds.value = agent.value.knowledge_base_ids
  const [kbRes, llmRes] = await Promise.all([kbApi.list(), configApi.llmOptions()])
  kbs.value = kbRes
  llmOptions.value = llmRes.items
  modelId.value = llmRes.default_id
  topK.value = agent.value.top_k
  retrievalFirst.value = agent.value.retrieval_first
}

async function refreshConversations() {
  conversations.value = await agentApi.conversations(agentId)
}

function newConversation() {
  conversationId.value = null
  messages.value = []
  citations.value = []
  notice.value = ''
  resetScrollState()
}

async function openConversation(id: number) {
  conversationId.value = id
  messages.value = await agentApi.messages(id)
  const last = [...messages.value].reverse().find((m) => m.role === 'assistant')
  citations.value = last?.citations ?? []
  resetScrollState()
  nextTick(() => scrollToBottom(false))
}

// ---------- 滚动策略 ----------
// 只有用户本来就贴着底部时才自动跟滚；向上翻历史时不把人拽回来。
const SCROLL_GAP = 64
const stickBottom = ref(true)
const showJump = ref(false)
let scrollRaf = 0

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight
  stickBottom.value = gap < SCROLL_GAP
  showJump.value = !stickBottom.value
}

function resetScrollState() {
  stickBottom.value = true
  showJump.value = false
}

function scrollToBottom(smooth = true) {
  const el = scrollEl.value
  if (!el || !stickBottom.value) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

/** 流式期间一帧最多滚一次，避免每个 token 都触发一次布局抖动 */
function scheduleScroll() {
  if (scrollRaf) return
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0
    scrollToBottom(false)
  })
}

function jumpToBottom() {
  resetScrollState()
  nextTick(() => scrollToBottom(true))
}

// ---------- 流式输出合帧 ----------
// 模型每秒能吐几十个 delta。逐条更新会带来两笔开销：整段 markdown 重新渲染 + 滚动，
// 回答越长越卡。这里按 60ms 合帧，一批一起刷。
const FLUSH_MS = 60
let deltaBuf = ''
let flushTimer: number | null = null

function flushDelta(reply: ChatMessage) {
  if (!deltaBuf) return
  reply.content += deltaBuf
  deltaBuf = ''
}

function scheduleFlush(reply: ChatMessage) {
  if (flushTimer != null) return
  flushTimer = window.setTimeout(() => {
    flushTimer = null
    flushDelta(reply)
    scrollToBottom(false)
  }, FLUSH_MS)
}

function cancelFlush() {
  if (flushTimer != null) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
}

async function ask(q: string) {
  input.value = q
  await send()
}

async function send() {
  const question = input.value.trim()
  if (!question || streaming.value) return
  input.value = ''
  notice.value = ''

  messages.value.push({ role: 'user', content: question })
  // 用 reactive 包一层再 push：直接改裸对象的属性不会触发更新（读的是代理，写的是原对象）
  const reply = reactive<ChatMessage>({ role: 'assistant', content: '', citations: [] })
  messages.value.push(reply)
  streaming.value = true
  resetScrollState()
  nextTick(() => scrollToBottom(false))

  abort = new AbortController()
  try {
    await streamChat(
      agentId,
      {
        question,
        conversation_id: conversationId.value,
        model_config_id: modelId.value || undefined,
        knowledge_base_ids: kbIds.value,
        top_k: topK.value,
        retrieval_first: retrievalFirst.value,
        use_keyword: useKeyword.value,
      },
      {
        onStart: (d) => {
          conversationId.value = d.conversation_id
        },
        onRetrieval: (d) => {
          if (d.note) notice.value = d.note
        },
        onCitations: (d) => {
          citations.value = d.items as Citation[]
        },
        onReasoning: (d) => {
          reply.reasoning = (reply.reasoning || '') + d.text
          scheduleScroll()
        },
        onDelta: (d) => {
          deltaBuf += d.text
          scheduleFlush(reply)
        },
        onNotice: (d) => {
          notice.value = d.message
        },
        onError: (d) => {
          ElMessage.error(d.message)
          reply.is_error = true
        },
        onDone: (d) => {
          reply.latency_ms = Number(d.latency_ms ?? 0)
          reply.model_name = String(d.model ?? agent.value?.model_name ?? '')
        },
      },
      abort.signal,
    )
  } catch {
    /* 中断或网络错误已在 onError 里提示 */
  } finally {
    // 收尾必须把缓冲区里剩下的字刷出来，否则最后几十毫秒的内容会丢
    cancelFlush()
    flushDelta(reply)
    streaming.value = false
    abort = null
    refreshConversations()
  }
}

function stop() {
  abort?.abort()
}

async function rate(m: ChatMessage, rating: 'like' | 'dislike') {
  if (!m.id) return
  await agentApi.feedback(m.id, rating)
  m.feedback = rating
  ElMessage.success('感谢反馈')
}

onMounted(loadAll)
</script>

<style scoped lang="scss">
.chat-wrap {
  display: flex;
  /* 高度由布局层统一算好（el-main 上下各 16px padding 要扣掉）。
     写死 calc(100vh - 60px) 会多出 32px，外层的 .main 就冒出滚动条。 */
  height: var(--content-height, calc(100vh - 92px));
  background: var(--bg-page);
  border-radius: var(--radius);
  overflow: hidden;
}

.side {
  width: 240px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;

  .new-btn {
    margin: 12px;
  }

  .conv-list {
    flex: 1;
    overflow-y: auto;
  }

  .conv-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    cursor: pointer;
    font-size: 13px;
    color: var(--ink-2);
    border-left: 2px solid transparent;
    transition: background-color 0.18s var(--ease), color 0.18s var(--ease),
      border-color 0.18s var(--ease);

    &:hover {
      background: var(--bg-page);
    }

    &.active {
      background: #ecf5ff;
      color: var(--brand);
      border-left-color: var(--brand);
    }

    .ctitle {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  &.right {
    width: 320px;
    border-right: none;
    border-left: 1px solid #e4e7ed;

    .cite-head {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 14px;
      border-bottom: 1px solid #e4e7ed;
    }

    .cite-list {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }
  }
}

.citation-item {
  .cite-top {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 13px;
    font-weight: 600;

    .src {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .path {
    margin: 4px 0;
    color: #409eff;
    font-size: 12px;
  }

  .snippet {
    color: #606266;
    font-size: 12px;
    line-height: 1.6;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .scores {
    margin-top: 6px;
    color: #909399;
    font-size: 11px;
    display: flex;
    gap: 6px;
    align-items: center;
  }
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;

  .chat-head {
    padding: 14px 20px;
    background: #fff;
    border-bottom: 1px solid #e4e7ed;

    .muted {
      margin-left: 10px;
      color: #909399;
      font-size: 12px;
    }
  }

  .messages-wrap {
    position: relative;
    flex: 1;
    min-height: 0;
    min-width: 0;
    display: flex;
  }

  .jump-btn {
    position: absolute;
    left: 50%;
    bottom: 14px;
    transform: translateX(-50%);
    z-index: 3;
    box-shadow: 0 4px 14px rgba(31, 45, 61, 0.18);
  }

  .jump-enter-active,
  .jump-leave-active {
    transition: opacity 0.2s var(--ease), transform 0.2s var(--ease);
  }

  .jump-enter-from,
  .jump-leave-to {
    opacity: 0;
    transform: translate(-50%, 10px);
  }

  .messages {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    padding: 20px;

    .welcome {
      text-align: center;
      margin-top: 80px;
      animation: fade-up 0.45s var(--ease) both;

      h3 {
        font-weight: 500;
        color: var(--ink-2);
      }

      .sug {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
        margin-top: 16px;
      }
    }

    .msg {
      display: flex;
      margin-bottom: 16px;
      /* 新气泡入场；流式刷新不会重挂载，所以动画不会反复播 */
      animation: bubble-in 0.28s var(--ease) both;

      &.user {
        justify-content: flex-end;

        .bubble {
          background: var(--brand);
          color: #fff;
          box-shadow: 0 2px 8px rgba(64, 158, 255, 0.22);
        }
      }

      &.assistant .bubble {
        background: #fff;
        box-shadow: var(--shadow-1);
      }

      .bubble {
        max-width: 78%;
        padding: 12px 16px;
        border-radius: 10px;
        font-size: 14px;

        .reasoning {
          padding: 8px 10px;
          margin-bottom: 8px;
          background: var(--bg-page);
          border-left: 3px solid #c0c4cc;
          border-radius: 0 4px 4px 0;
          color: var(--ink-3);
          font-size: 12px;
          line-height: 1.6;
          white-space: pre-wrap;
          max-height: 180px;
          overflow-y: auto;
        }

        /* 代码块/表格/标题等排版统一在全局 .answer-md 里（v-html 内容需要全局选择器） */
        .md {
          min-width: 0;
        }

        .meta {
          margin-top: 8px;
          color: var(--ink-3);
          font-size: 12px;
          display: flex;
          align-items: center;
          gap: 4px;
          opacity: 0;
          animation: fade-up 0.3s var(--ease) 0.1s forwards;
        }
      }
    }
  }

  .notice {
    margin: 0 20px 8px;
    padding: 8px 12px;
    background: #fdf6ec;
    color: #e6a23c;
    border-radius: var(--radius-sm);
    font-size: 12px;
    animation: fade-up 0.28s var(--ease) both;
  }

  .input-area {
    background: #fff;
    border-top: 1px solid #e4e7ed;
    padding: 12px 20px;

    .opts {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-top: 10px;

      .opt-label {
        margin-left: 4px;
        max-width: 420px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }
  }
}

.param-panel {
  .param-item {
    margin-bottom: 14px;

    &:last-child {
      margin-bottom: 0;
    }

    .param-label {
      font-size: 13px;
      color: #606266;
      margin-bottom: 6px;
    }

    &.param-switches {
      display: flex;
      gap: 16px;
    }
  }
}
</style>
