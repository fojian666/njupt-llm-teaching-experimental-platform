<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auditApi } from '@/api/agents'
import CountUp from '@/components/CountUp.vue'
import type { QARecord, OperationLog } from '@/types'

const tab = ref('records')

// ---------------- 问答记录 ----------------
const records = ref<QARecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const filters = reactive({
  keyword: '', feedback: '', only_error: false,
  dateRange: null as [string, string] | null,
})
const detail = ref<QARecord | null>(null)
const detailDialog = ref(false)

async function loadRecords() {
  loading.value = true
  try {
    const r = await auditApi.records({
      page: page.value,
      page_size: pageSize,
      keyword: filters.keyword || undefined,
      feedback: filters.feedback || undefined,
      only_error: filters.only_error || undefined,
      date_from: filters.dateRange?.[0],
      date_to: filters.dateRange?.[1],
    })
    records.value = r.items
    total.value = r.total
  } finally { loading.value = false }
}
function showDetail(row: QARecord) {
  detail.value = row
  detailDialog.value = true
}
function resetFilters() {
  filters.keyword = ''
  filters.feedback = ''
  filters.only_error = false
  filters.dateRange = null
  page.value = 1
  loadRecords()
}

// ---------------- 操作日志 ----------------
const logs = ref<OperationLog[]>([])
const logsLoading = ref(false)
const logAction = ref('')
const actionOptions = ref<{ action: string; count: number }[]>([])

async function loadLogs() {
  logsLoading.value = true
  try {
    const r = await auditApi.logs({ page_size: 100, action: logAction.value || undefined })
    logs.value = r.items
  } finally { logsLoading.value = false }
}
async function loadActions() {
  const r = await auditApi.logActions()
  actionOptions.value = r.items ?? []
}

// ---------------- 使用统计 ----------------
const stats = ref<Record<string, any> | null>(null)
const statsLoading = ref(false)
async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await auditApi.stats(7)
  } finally { statsLoading.value = false }
}

const feedbackLabel: Record<string, string> = { like: '👍 赞', dislike: '👎 踩' }
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
const feedbackType: Record<string, TagType> = { like: 'success', dislike: 'danger' }

/** 统计卡片：一次算好，模板里只负责渲染 + 错峰入场 */
interface StatCard {
  title: string
  value: number | null
  precision?: number
  suffix?: string
}
const statCards = computed<StatCard[]>(() => {
  const s = stats.value
  if (!s) return []
  return [
    { title: '问答总数', value: s.total_qa },
    { title: '近 7 天问答', value: s.recent_qa },
    { title: '报错问答', value: s.error_qa },
    { title: '会话总数', value: s.conversations },
  ]
})
const statCards2 = computed<StatCard[]>(() => {
  const s = stats.value
  if (!s) return []
  return [
    { title: '点赞数', value: s.liked },
    { title: '点踩数', value: s.disliked },
    { title: '满意度', value: s.satisfaction != null ? s.satisfaction * 100 : null, precision: 1, suffix: '%' },
    { title: '平均耗时', value: s.avg_latency_ms ? s.avg_latency_ms / 1000 : null, precision: 1, suffix: 's' },
  ]
})
const exporting = ref(false)
async function exportRecords() {
  if (exporting.value) return
  exporting.value = true
  try {
    // 循环拉取全部符合条件的记录（按当前筛选），导出为 JSON 文件
    const all: QARecord[] = []
    let p = 1
    for (;;) {
      const r = await auditApi.records({
        page: p,
        page_size: 100,
        keyword: filters.keyword || undefined,
        feedback: filters.feedback || undefined,
        only_error: filters.only_error || undefined,
        date_from: filters.dateRange?.[0],
        date_to: filters.dateRange?.[1],
      })
      all.push(...r.items)
      if (!r.items.length || all.length >= r.total) break
      p++
    }
    const blob = new Blob([JSON.stringify(all, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `qa-records-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success(`已导出 ${all.length} 条记录`)
  } finally {
    exporting.value = false
  }
}

onMounted(() => { loadRecords(); loadStats() })
function switchTab(name: string | number) {
  if (name === 'logs') { if (!logs.value.length) { loadLogs(); loadActions() } }
  if (name === 'stats') { if (!stats.value) loadStats() }
}
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never">
    <el-tabs v-model="tab" @tab-change="switchTab">
      <!-- 问答记录 -->
      <el-tab-pane label="问答记录" name="records">
        <el-form inline class="mb16">
          <el-form-item label="关键词">
            <el-input v-model="filters.keyword" placeholder="搜问题 / 会话标题" clearable style="width: 220px" @keyup.enter="loadRecords" @clear="loadRecords" />
          </el-form-item>
          <el-form-item label="反馈">
            <el-select v-model="filters.feedback" clearable placeholder="全部" style="width: 120px" @change="loadRecords">
              <el-option label="👍 赞" value="like" />
              <el-option label="👎 踩" value="dislike" />
            </el-select>
          </el-form-item>
          <el-form-item label="日期">
            <el-date-picker
              v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD"
              start-placeholder="开始" end-placeholder="结束" style="width: 240px" @change="loadRecords"
            />
          </el-form-item>
          <el-form-item label="只看报错">
            <el-switch v-model="filters.only_error" @change="loadRecords" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="loadRecords">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
            <el-button :loading="exporting" @click="exportRecords">导出 JSON</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="records" size="small" border>
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column prop="user_name" label="用户" width="100" />
          <el-table-column prop="agent_name" label="智能体" width="120" show-overflow-tooltip />
          <el-table-column prop="question" label="问题" min-width="200" show-overflow-tooltip />
          <el-table-column label="回答" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ (row.answer || '').slice(0, 80) }}{{ (row.answer || '').length > 80 ? '…' : '' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="引用" width="80">
            <template #default="{ row }">{{ row.cited_count }}/{{ row.citation_count }}</template>
          </el-table-column>
          <el-table-column label="反馈" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.feedback" :type="feedbackType[row.feedback]" size="small">{{ feedbackLabel[row.feedback] }}</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="80">
            <template #default="{ row }">
              <span v-if="row.latency_ms">{{ (row.latency_ms / 1000).toFixed(1) }}s</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="showDetail(row as QARecord)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="page" class="mt16"
          layout="total, prev, pager, next" :total="total" :page-size="pageSize"
          @current-change="loadRecords"
        />
      </el-tab-pane>

      <!-- 操作日志 -->
      <el-tab-pane label="操作日志" name="logs">
        <el-form inline class="mb16">
          <el-form-item label="操作类型">
            <el-select v-model="logAction" clearable placeholder="全部" style="width: 220px" @change="loadLogs">
              <el-option v-for="a in actionOptions" :key="a.action" :label="`${a.action}（${a.count}）`" :value="a.action" />
            </el-select>
          </el-form-item>
          <el-form-item><el-button type="primary" @click="loadLogs">查询</el-button></el-form-item>
        </el-form>
        <el-table v-loading="logsLoading" :data="logs" size="small" border>
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column prop="user_name" label="用户" width="120" />
          <el-table-column prop="action" label="动作" width="160" />
          <el-table-column label="对象" width="160">
            <template #default="{ row }">{{ row.target_type }}#{{ row.target_id }}</template>
          </el-table-column>
          <el-table-column label="详情" min-width="260">
            <template #default="{ row }">
              <span class="muted">{{ JSON.stringify(row.detail) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="ip" label="IP" width="130" />
        </el-table>
      </el-tab-pane>

      <!-- 使用统计 -->
      <el-tab-pane label="使用统计" name="stats">
        <div v-if="stats" v-loading="statsLoading">
          <el-row :gutter="16" class="stat-row">
            <el-col v-for="(s, i) in statCards" :key="s.title" :span="6" :style="{ '--i': i }">
              <el-card shadow="never" class="stat-card">
                <CountUp :title="s.title" :value="s.value" :precision="s.precision" :suffix="s.suffix" />
              </el-card>
            </el-col>
          </el-row>
          <el-row :gutter="16" class="stat-row">
            <el-col v-for="(s, i) in statCards2" :key="s.title" :span="6" :style="{ '--i': i + 4 }">
              <el-card shadow="never" class="stat-card">
                <CountUp :title="s.title" :value="s.value" :precision="s.precision" :suffix="s.suffix" />
              </el-card>
            </el-col>
          </el-row>
          <el-card shadow="never">
            <template #header>近 7 天智能体问答分布</template>
            <el-table :data="stats.by_agent ?? []" size="small" border>
              <el-table-column prop="name" label="智能体" min-width="180" />
              <el-table-column prop="count" label="问答次数" width="120" />
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
    </el-card>

    <el-dialog v-model="detailDialog" title="问答详情" width="720" top="6vh">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small" class="mb16">
          <el-descriptions-item label="时间">{{ detail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ detail.user_name }}</el-descriptions-item>
          <el-descriptions-item label="智能体">{{ detail.agent_name }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ detail.model_name }}</el-descriptions-item>
          <el-descriptions-item label="引用（已标注/总数）">{{ detail.cited_count }} / {{ detail.citation_count }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ detail.latency_ms ? (detail.latency_ms / 1000).toFixed(1) + 's' : '—' }}</el-descriptions-item>
        </el-descriptions>
        <div class="detail-q">{{ detail.question }}</div>
        <div class="detail-a">{{ detail.answer }}</div>
        <div v-if="detail.citations?.length" class="detail-cites">
          <div class="cites-title">检索来源</div>
          <div v-for="c in detail.citations" :key="c.chunk_id" class="cite-item">
            <el-tag :type="c.cited ? 'success' : 'info'" size="small">[{{ c.index }}]{{ c.cited ? ' 已引用' : '' }}</el-tag>
            <b class="ml8">{{ c.source_name }}</b>
            <span class="muted ml8">{{ c.chapter_path }}</span>
            <div class="cite-body">{{ c.snippet }}</div>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mt16 { margin-top: 16px; }
.mb16 { margin-bottom: 16px; }
.ml8 { margin-left: 8px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.stat-row { margin-bottom: 16px; }
/* 统计卡片错峰入场：--i 由模板注入序号。
   填充用 backwards：用 both 的话填充值会压掉下面 :hover 的 transform。
   注意本文件 style 块没写 lang="scss"，这里只能是平铺 CSS，不能用嵌套。 */
.stat-card {
  animation: card-in 0.4s var(--ease) backwards;
  animation-delay: calc(var(--i, 0) * 60ms);
  transition: transform 0.22s var(--ease), box-shadow 0.22s var(--ease);
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-1);
}
.stat-none { color: var(--el-text-color-secondary); font-size: 14px; text-align: center; }
.detail-q { background: var(--el-fill-color-light); border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; font-weight: 600; }
.detail-a { white-space: pre-wrap; line-height: 1.7; font-size: 13px; }
.detail-cites { margin-top: 16px; border-top: 1px dashed var(--el-border-color); padding-top: 12px; }
.cites-title { font-weight: 600; margin-bottom: 8px; }
.cite-item { margin-bottom: 10px; }
.cite-body { font-size: 12px; color: var(--el-text-color-regular); margin-top: 4px; }
</style>
