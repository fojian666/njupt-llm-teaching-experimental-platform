<template>
  <div class="side right">
    <div class="cite-head">
      <b>检索来源</b>
      <span class="count">{{ citations.length }}</span>
    </div>
    <div class="cite-list">
      <div
        v-for="c in citations"
        :key="`${c.chunk_id}-${c.index}`"
        class="citation-item"
        :class="{ 'is-cited': c.cited }"
        :style="{ '--i': Math.min(c.index, 10) }"
        :title="`查看切片 [#${c.index}] 全文`"
        :aria-label="`查看引用 ${c.index} 的切片全文`"
        role="button"
        tabindex="0"
        @click="openCitation(c)"
        @keydown.enter.prevent="openCitation(c)"
        @keydown.space.prevent="openCitation(c)"
      >
        <div class="cite-top">
          <span class="idx">[{{ c.index }}]</span>
          <span class="src">{{ c.source_name }}</span>
          <el-icon class="open-ico"><ArrowRight /></el-icon>
        </div>
        <div class="path">{{ c.chapter_path || '（无章节路径）' }}</div>
        <div class="snippet">{{ c.snippet }}</div>
        <div class="scores">
          综合 {{ c.score.toFixed(3) }} · 向量 {{ c.vector_score.toFixed(3) }} · 关键词 {{ c.lexical_score.toFixed(3) }}
          <span v-if="c.cited" class="cited-tag">已引用</span>
        </div>
      </div>
      <el-empty v-if="!citations.length" description="尚未检索" :image-size="60" />
    </div>

    <!-- 切片全文：面板上的内容是截断的，这里按 chunk_id 取回完整切片 -->
    <el-drawer v-model="drawer" size="560px" :title="`切片详情 [#${chunk?.seq ?? ''}]`" append-to-body>
      <div v-loading="loading">
        <el-descriptions v-if="current" :column="1" border size="small">
          <el-descriptions-item label="来源文件">{{ current.source_name }}</el-descriptions-item>
          <el-descriptions-item label="章节路径">{{ current.chapter_path || '（无章节路径）' }}</el-descriptions-item>
          <el-descriptions-item label="切片编号">#{{ current.index }}</el-descriptions-item>
          <el-descriptions-item label="相关度">
            综合 {{ current.score.toFixed(3) }} · 向量 {{ current.vector_score.toFixed(3) }} · 关键词 {{ current.lexical_score.toFixed(3) }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="cite-body-head">
          <span>切片全文</span>
          <el-button link size="small" @click="copyChunk">复制</el-button>
        </div>
        <pre class="cite-body">{{ chunk?.content || '加载中…' }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
/**
 * 右侧检索来源面板。
 *
 * 面板里只展示截断片段，点开抽屉时按 chunk_id 取回完整切片；
 * 切片已被删除时给出提示并关闭抽屉，不把错误留在界面上。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { kbApi } from '@/api/datasets'
import type { Chunk, Citation } from '@/types'

defineProps<{ citations: Citation[] }>()

const drawer = ref(false)
const loading = ref(false)
const current = ref<Citation | null>(null)
const chunk = ref<Chunk | null>(null)

async function openCitation(c: Citation) {
  current.value = c
  chunk.value = null
  drawer.value = true
  loading.value = true
  try {
    chunk.value = await kbApi.chunk(c.chunk_id)
  } catch {
    ElMessage.error('切片已不存在，可能已被删除或移出知识库')
    drawer.value = false
  } finally {
    loading.value = false
  }
}

async function copyChunk() {
  const text = chunk.value?.content
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制切片全文')
  } catch {
    ElMessage.warning('浏览器拒绝了剪贴板访问')
  }
}
</script>

<style scoped lang="scss">
.side {
  display: flex;
  flex-direction: column;

  &.right {
    width: 316px;
    background: var(--bg-soft);
    border-left: 1px solid var(--line-soft);

    .cite-head {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 10px;

      .count {
        padding: 1px 8px;
        border-radius: var(--radius-pill);
        background: var(--bg-hover-strong);
        color: var(--ink-2);
        font-size: 12px;
        font-variant-numeric: tabular-nums;
      }
    }

    .cite-list {
      flex: 1;
      overflow-y: auto;
      padding: 4px 12px 16px;
    }
  }
}

.citation-item {
  border-radius: var(--radius-lg);
  border: 1px solid var(--line);
  background: #fff;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;

  &:hover,
  &:focus-visible {
    border-color: var(--brand-line);
    box-shadow: 0 2px 10px rgba(0, 122, 255, 0.12);
    outline: none;

    .open-ico {
      opacity: 1;
      transform: translateX(2px);
    }
  }

  .open-ico {
    margin-left: auto;
    color: var(--brand);
    opacity: 0;
    transition: opacity 0.15s, transform 0.15s;
  }

  .cite-top {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 13px;
    font-weight: 600;

    .idx {
      font-variant-numeric: tabular-nums;
      color: var(--brand-ink);
    }

    .src {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .path {
    margin: 4px 0;
    color: var(--brand-ink);
    font-size: 12px;
  }

  .snippet {
    color: var(--ink-2);
    font-size: 12px;
    line-height: 1.62;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .scores {
    margin-top: 8px;
    color: var(--ink-3);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    display: flex;
    gap: 6px;
    align-items: center;

    .cited-tag {
      padding: 1px 7px;
      border-radius: var(--radius-pill);
      background: var(--ok-soft);
      color: var(--ok);
      font-size: 11px;
    }
  }
}

/* 抽屉内容在组件模板里，但 teleport 到 body —— 选择器不要嵌在上层类名里 */
.cite-body-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
}

.cite-body {
  margin: 0;
  padding: 14px;
  max-height: 46vh;
  overflow: auto;
  background: #fafbfc;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-1);
}
</style>
