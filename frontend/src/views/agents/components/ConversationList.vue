<template>
  <div class="side">
    <div class="side-head">
      <el-input v-model="keyword" placeholder="搜索会话" clearable size="small" style="margin-bottom: 8px" />
      <el-button type="primary" class="new-btn" @click="emit('create')">新建会话</el-button>
    </div>
    <div class="conv-list">
      <template v-for="g in groups" :key="g.label">
        <div class="conv-group">{{ g.label }}</div>
        <div
          v-for="c in g.items"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === activeId }"
          @click="emit('open', c.id)"
        >
          <span class="ctitle">{{ c.title || '新会话' }}</span>
          <button class="conv-del" title="删除会话" @click.stop="emit('remove', c)">
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </template>
      <el-empty v-if="!groups.length" description="暂无会话" :image-size="54" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 会话历史侧栏：搜索 + 按今天/近七天/更早分组。
 *
 * 分组与搜索都在这里算，父组件只负责给数据和处理「打开 / 删除 / 新建」三件事。
 */
import { computed, ref } from 'vue'
import type { Conversation } from '@/types'

const props = defineProps<{
  conversations: Conversation[]
  activeId: number | null
}>()

const emit = defineEmits<{
  open: [id: number]
  remove: [c: Conversation]
  create: []
}>()

const keyword = ref('')

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return props.conversations
  return props.conversations.filter((c) => (c.title || '').toLowerCase().includes(kw))
})

const groups = computed(() => {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const sevenDaysAgo = startOfToday - 6 * 86_400_000
  const out: { label: string; items: Conversation[] }[] = [
    { label: '今天', items: [] },
    { label: '近七天', items: [] },
    { label: '更早', items: [] },
  ]
  for (const c of filtered.value) {
    const t = new Date(String(c.updated_at).replace(' ', 'T')).getTime()
    if (!Number.isFinite(t) || t < sevenDaysAgo) out[2].items.push(c)
    else if (t >= startOfToday) out[0].items.push(c)
    else out[1].items.push(c)
  }
  return out.filter((g) => g.items.length)
})
</script>

<style scoped lang="scss">
.side {
  width: 232px;
  background: #fbfbfd; /* iOS 侧栏那种极淡的灰 */
  border-right: 1px solid rgba(60, 60, 67, 0.08);
  display: flex;
  flex-direction: column;

  .side-head {
    padding: 12px;
  }

  .new-btn {
    width: 100%;
    border-radius: 10px;
  }

  .conv-list {
    flex: 1;
    overflow-y: auto;
    padding: 0 8px 12px;
  }

  /* 选中态用圆角灰底（iOS 列表风格），不用左侧色条 —— 色条太"管理后台"了 */
  .conv-group {
    padding: 10px 10px 4px;
    font-size: 11px;
    color: var(--ink-3);
  }

  .conv-item {
    position: relative;
    display: flex;
    align-items: center;
    padding: 9px 10px;
    margin-bottom: 2px;
    border-radius: 9px;
    cursor: pointer;
    font-size: 13px;
    color: var(--ink-2);
    transition: background-color 0.16s var(--ease), color 0.16s var(--ease);

    &:hover {
      background: rgba(120, 120, 128, 0.08);
    }

    &.active {
      background: rgba(0, 122, 255, 0.1);
      color: var(--brand-ink);
      font-weight: 500;
    }

    .ctitle {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      /* 右侧常留出删除钮的位置，避免标题文字被压在按钮底下 */
      padding-right: 20px;
    }

    /* 删除钮：悬停才出现，像 iOS 列表的滑出操作 */
    .conv-del {
      position: absolute;
      right: 6px;
      top: 50%;
      transform: translateY(-50%);
      display: grid;
      place-items: center;
      padding: 4px;
      border: none;
      border-radius: 6px;
      background: transparent;
      color: var(--ink-3);
      font-size: 13px;
      cursor: pointer;
      opacity: 0;
      transition: opacity 0.15s var(--ease), color 0.15s var(--ease),
        background-color 0.15s var(--ease);

      &:hover {
        color: #e5484d;
        background: rgba(229, 72, 77, 0.1);
      }
    }

    &:hover .conv-del {
      opacity: 1;
    }
  }
}
</style>
