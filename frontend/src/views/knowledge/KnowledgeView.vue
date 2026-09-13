<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { kbApi, resourceApi } from '@/api/datasets'
import type { KnowledgeBase, KnowledgeDoc, Chunk, Citation, DataResource } from '@/types'

// ---------------- 知识库 ----------------
const kbs = ref<KnowledgeBase[]>([])
const current = ref<KnowledgeBase | null>(null)
const loading = ref(false)

const kbDialog = ref(false)
const kbFormRef = ref<FormInstance>()
const kbRules: FormRules = {
  name: [
    { required: true, message: '请填写知识库名称', trigger: 'blur' },
    { max: 128, message: '名称不能超过 128 个字', trigger: 'blur' },
  ],
}
const kbForm = reactive<Record<string, any>>({
  id: 0, name: '', code: '', description: '',
  chunk_size: 500, chunk_overlap: 80, chunk_strategy: 'heading',
  embedding_model_id: null as number | null,
})

async function loadKBs() {
  loading.value = true
  try {
    kbs.value = await kbApi.list()
    if (current.value) {
      current.value = kbs.value.find((k) => k.id === current.value!.id) ?? null
    }
  } finally { loading.value = false }
}
function openCreateKB() {
  Object.assign(kbForm, { id: 0, name: '', code: '', description: '', chunk_size: 500, chunk_overlap: 80, chunk_strategy: 'heading', embedding_model_id: null })
  kbDialog.value = true
}
function openEditKB() {
  const kb = current.value
  if (!kb) return
  Object.assign(kbForm, {
    id: kb.id, name: kb.name, code: kb.code, description: kb.description,
    chunk_size: kb.chunk_size, chunk_overlap: kb.chunk_overlap, chunk_strategy: kb.chunk_strategy,
    embedding_model_id: kb.embedding_model_id,
  })
  kbDialog.value = true
}
async function saveKB() {
  const ok = await kbFormRef.value?.validate().then(() => true).catch(() => false)
  if (!ok) return
  const payload = { ...kbForm }
  if (!kbForm.id) delete payload.id
  if (kbForm.id) await kbApi.update(kbForm.id, payload)
  else await kbApi.create(payload)
  ElMessage.success('已保存')
  kbDialog.value = false
  loadKBs()
}
async function removeKB(kb: KnowledgeBase) {
  await ElMessageBox.confirm(`删除知识库「${kb.name}」？知识条目会一并移除（数据管理里的原始数据保留）。`, '确认', { type: 'warning' })
  await kbApi.remove(kb.id)
  if (current.value?.id === kb.id) current.value = null
  loadKBs()
}
function selectKB(kb: KnowledgeBase) {
  current.value = kb
  page.value = 1
  loadDocs()
}

// ---------------- 知识条目（来自数据管理导入） ----------------
const docs = ref<KnowledgeDoc[]>([])
const docTotal = ref(0)
const page = ref(1)
const pageSize = 20
const docsLoading = ref(false)
const docKeyword = ref('')

async function loadDocs() {
  if (!current.value) return
  docsLoading.value = true
  try {
    const r = await kbApi.docs(current.value.id, { page: page.value, page_size: pageSize, keyword: docKeyword.value })
    docs.value = r.items
    docTotal.value = r.total
  } finally { docsLoading.value = false }
}

async function toggleDoc(doc: KnowledgeDoc) {
  const r = await kbApi.toggleDoc(doc.id)
  doc.is_active = (r.data as any).is_active
  ElMessage.success((r.data as any).message)
}
async function reparse(doc: KnowledgeDoc) {
  await kbApi.reparse(doc.id)
  ElMessage.success('已提交重新解析入库')
  loadDocs()
}
async function embedDoc(doc: KnowledgeDoc) {
  await kbApi.embed(doc.id)
  ElMessage.success('已提交向量化')
  loadDocs()
}
async function removeDoc(doc: KnowledgeDoc) {
  await ElMessageBox.confirm(`从知识库移除「${doc.name}」？切片会一并删除。`, '确认', { type: 'warning' })
  await kbApi.removeDoc(doc.id)
  loadDocs()
  loadKBs()
}

// ---------------- 切片预览 ----------------
const chunkDialog = ref(false)
const currentDoc = ref<KnowledgeDoc | null>(null)
const chunks = ref<Chunk[]>([])
const chunksLoading = ref(false)
async function showChunks(doc: KnowledgeDoc) {
  currentDoc.value = doc
  chunkDialog.value = true
  chunksLoading.value = true
  try {
    const r = await kbApi.chunks(doc.id, { page_size: 50 })
    chunks.value = r.items
  } finally { chunksLoading.value = false }
}

// ---------------- 章节大纲（平铺列表） ----------------
const outlineDialog = ref(false)
const outlineItems = ref<{ chapter_path: string; chunk_count: number }[]>([])
async function showOutline(doc: KnowledgeDoc) {
  currentDoc.value = doc
  const r = await kbApi.outline(doc.id)
  outlineItems.value = r.items ?? []
  outlineDialog.value = true
}

// ---------------- 检索调试 ----------------
const searchForm = reactive({ query: '', alpha: 0.7, use_keyword: true, top_k: 5 })
const hits = ref<Citation[]>([])
const searchMeta = reactive({ vector_count: 0, lexical_count: 0, note: '' })
const searching = ref(false)
async function doSearch() {
  if (!current.value || !searchForm.query.trim()) return
  searching.value = true
  try {
    const r = await kbApi.search({
      query: searchForm.query,
      knowledge_base_ids: [current.value.id],
      top_k: searchForm.top_k,
      alpha: searchForm.alpha,
      use_keyword: searchForm.use_keyword,
    })
    hits.value = r.items ?? []
    searchMeta.vector_count = r.vector_count
    searchMeta.lexical_count = r.lexical_count
    searchMeta.note = r.note
  } finally { searching.value = false }
}

// ---------------- 从数据管理导入 ----------------
const importDialog = ref(false)
const importRows = ref<DataResource[]>([])
const importSelected = ref<DataResource[]>([])
const importLoading = ref(false)
const importKeyword = ref('')

async function openImport() {
  if (!current.value) return
  importDialog.value = true
  importLoading.value = true
  try {
    const r = await resourceApi.list({ page: 1, page_size: 200, status: 'success', keyword: importKeyword.value || undefined })
    // 排除已导入当前知识库的
    importRows.value = (r.items ?? []).filter((x) => !x.in_knowledge_bases.includes(current.value!.name))
  } finally {
    importLoading.value = false
  }
}
async function doImport() {
  if (!current.value || !importSelected.value.length) return
  const r = await kbApi.importResources(current.value.id, importSelected.value.map((x) => x.id))
  ElMessage.success((r.data as any).message || '已导入')
  importDialog.value = false
  loadDocs()
  loadKBs()
}

onMounted(loadKBs)
</script>

<template>
  <div v-loading="loading">
    <!-- 知识库列表 -->
    <el-card shadow="never" class="mb16">
      <template #header>
        <div class="card-head">
          <span>知识库{{ current ? ` · 当前：${current.name}` : '' }}</span>
          <el-button type="primary" @click="openCreateKB">新建知识库</el-button>
        </div>
      </template>
      <el-empty v-if="!kbs.length" description="暂无知识库" />
      <div v-else class="kb-grid">
        <div v-for="kb in kbs" :key="kb.id" class="kb-card" :class="{ active: current?.id === kb.id }" @click="selectKB(kb)">
          <div class="kb-name">{{ kb.name }}</div>
          <div class="kb-desc">{{ kb.description || '—' }}</div>
          <div class="kb-meta">
            <el-tag size="small">文档 {{ kb.doc_count }}</el-tag>
            <el-tag size="small" type="success">切片 {{ kb.chunk_count }}</el-tag>
            <el-tag size="small" type="info">{{ kb.embedding_model_name || '默认向量模型' }}</el-tag>
          </div>
          <div v-if="kb.warning" class="kb-warning">{{ kb.warning }}</div>
          <div class="kb-actions" @click.stop>
            <el-button size="small" link @click.stop="openEditKB">编辑</el-button>
            <el-button size="small" link type="danger" @click="removeKB(kb)">删除</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 知识条目 -->
    <el-card v-if="current" shadow="never" class="mb16">
      <template #header>
        <div class="card-head">
          <span>知识条目（来自「数据管理」导入）</span>
          <div class="head-tools">
            <el-input v-model="docKeyword" placeholder="搜索文档名" clearable style="width: 200px" @keyup.enter="loadDocs" @clear="loadDocs" />
            <el-button @click="loadDocs">刷新</el-button>
            <el-button type="primary" @click="openImport">从数据管理导入</el-button>
          </div>
        </div>
      </template>
      <el-table v-loading="docsLoading" :data="docs" size="small" border>
        <el-table-column prop="name" label="文档" min-width="200" show-overflow-tooltip />
        <el-table-column prop="category_path" label="分类" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.parse_status === 'failed' ? 'danger' : row.parse_status === 'indexed' ? 'success' : 'warning'" size="small">
              {{ row.parse_status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="切片数" width="80" />
        <el-table-column prop="char_count" label="字符数" width="90" />
        <el-table-column label="有效" width="70">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" size="small" @change="toggleDoc(row as KnowledgeDoc)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="showChunks(row as KnowledgeDoc)">切片</el-button>
            <el-button size="small" link type="primary" @click="showOutline(row as KnowledgeDoc)">大纲</el-button>
            <el-button size="small" link @click="reparse(row as KnowledgeDoc)">重解析</el-button>
            <el-button size="small" link @click="embedDoc(row as KnowledgeDoc)">补向量</el-button>
            <el-button size="small" link type="danger" @click="removeDoc(row as KnowledgeDoc)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" class="mt16" layout="total, prev, pager, next" :total="docTotal" :page-size="pageSize" @current-change="loadDocs" />
    </el-card>

    <!-- 检索调试 -->
    <el-card v-if="current" shadow="never">
      <template #header>检索调试（向量 + 关键词加权融合）</template>
      <el-form inline>
        <el-form-item label="测试问题">
          <el-input v-model="searchForm.query" style="width: 340px" placeholder="输入测试问题，回车检索" @keyup.enter="doSearch" />
        </el-form-item>
        <el-form-item label="向量权重 α">
          <el-slider v-model="searchForm.alpha" :min="0" :max="1" :step="0.1" style="width: 140px" />
        </el-form-item>
        <el-form-item label="关键词召回">
          <el-switch v-model="searchForm.use_keyword" />
        </el-form-item>
        <el-form-item label="Top K">
          <el-input-number v-model="searchForm.top_k" :min="1" :max="20" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="searching" @click="doSearch">检索</el-button>
        </el-form-item>
      </el-form>
      <div v-if="searchMeta.note" class="search-note">向量候选 {{ searchMeta.vector_count }} 条 · 关键词候选 {{ searchMeta.lexical_count }} 条 · {{ searchMeta.note }}</div>
      <div v-for="(h, i) in hits" :key="h.chunk_id" class="hit-item">
        <div class="hit-head">
          <el-tag size="small" type="warning">#{{ i + 1 }}</el-tag>
          <b class="ml8">{{ h.source_name }}</b>
          <span class="muted ml8">{{ h.chapter_path }}</span>
          <el-tag size="small" class="ml8">score {{ h.score.toFixed(4) }}</el-tag>
          <el-tag size="small" type="info" class="ml8">向量 {{ h.vector_score.toFixed(3) }} / 关键词 {{ h.lexical_score.toFixed(3) }}</el-tag>
        </div>
        <div class="hit-body">{{ h.snippet || h.content }}</div>
      </div>
      <el-empty v-if="!hits.length && !searching" description="暂无结果" :image-size="60" />
    </el-card>

    <el-dialog v-model="importDialog" :title="`导入数据到「${current?.name ?? ''}」`" width="720" top="6vh">
      <div class="head-tools" style="margin-bottom: 10px">
        <el-input v-model="importKeyword" placeholder="搜索数据名称" clearable style="width: 220px" @keyup.enter="openImport" />
        <el-button @click="openImport">搜索</el-button>
        <span class="muted" style="align-self: center">已选 {{ importSelected.length }} 条（只列出已解析成功的）</span>
      </div>
      <el-table
        v-loading="importLoading" :data="importRows" size="small" border max-height="420"
        @selection-change="(s: DataResource[]) => (importSelected = s)"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="name" label="数据名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="category_path" label="分类" min-width="140" show-overflow-tooltip />
        <el-table-column prop="file_format" label="格式" width="70" />
        <el-table-column prop="char_count" label="字符数" width="90" />
      </el-table>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!importSelected.length" @click="doImport">导入选中</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="kbDialog" :title="kbForm.id ? '编辑知识库' : '新建知识库'" width="520">
      <el-form ref="kbFormRef" :model="kbForm" :rules="kbRules" label-width="110">
        <el-form-item label="名称" prop="name"><el-input v-model="kbForm.name" maxlength="128" show-word-limit /></el-form-item>
        <el-form-item label="标识"><el-input v-model="kbForm.code" placeholder="唯一英文标识" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="kbForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="切片大小"><el-input-number v-model="kbForm.chunk_size" :min="100" :max="4000" :step="100" /></el-form-item>
        <el-form-item label="切片重叠"><el-input-number v-model="kbForm.chunk_overlap" :min="0" :max="1000" :step="20" /></el-form-item>
        <el-form-item label="切片策略">
          <el-select v-model="kbForm.chunk_strategy">
            <el-option label="按章节标题" value="heading" />
            <el-option label="固定长度" value="fixed" />
            <el-option label="段落语义" value="paragraph" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="kbDialog = false">取消</el-button>
        <el-button type="primary" @click="saveKB">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="chunkDialog" :title="`切片预览：${currentDoc?.name ?? ''}`" width="780" top="6vh">
      <el-table v-loading="chunksLoading" :data="chunks" size="small" border max-height="560">
        <el-table-column prop="seq" label="#" width="55" />
        <el-table-column prop="chapter_path" label="章节路径" min-width="160" show-overflow-tooltip />
        <el-table-column label="内容" min-width="330">
          <template #default="{ row }">
            <span class="chunk-text">{{ row.content.slice(0, 120) }}{{ row.content.length > 120 ? '…' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="向量" width="85">
          <template #default="{ row }">
            <el-tag :type="row.has_embedding ? 'success' : 'info'" size="small">{{ row.has_embedding ? '已向量化' : '无' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="char_count" label="字符" width="70" />
      </el-table>
    </el-dialog>

    <el-dialog v-model="outlineDialog" :title="`章节大纲：${currentDoc?.name ?? ''}`" width="560" top="6vh">
      <el-table :data="outlineItems" size="small" border max-height="480">
        <el-table-column prop="chapter_path" label="章节" min-width="280" />
        <el-table-column prop="chunk_count" label="切片数" width="90" />
      </el-table>
      <el-empty v-if="!outlineItems.length" description="无章节结构（文档未解析或无标题层级）" :image-size="60" />
    </el-dialog>
  </div>
</template>

<style scoped>
.mb16 { margin-bottom: 16px; }
.mt16 { margin-top: 16px; }
.ml8 { margin-left: 8px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.head-tools { display: flex; gap: 8px; }
.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
.kb-card { border: 1px solid var(--el-border-color); border-radius: 8px; padding: 14px; cursor: pointer; position: relative; transition: all 0.2s; }
.kb-card:hover { border-color: var(--el-color-primary); }
.kb-card.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.kb-name { font-weight: 600; margin-bottom: 6px; }
.kb-desc { font-size: 12px; color: var(--el-text-color-secondary); min-height: 32px; margin-bottom: 8px; }
.kb-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.kb-warning { margin-top: 8px; font-size: 12px; color: var(--el-color-danger); }
.kb-actions { position: absolute; right: 10px; top: 12px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.search-note { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 10px; }
.hit-item { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 10px; margin-bottom: 8px; }
.hit-head { display: flex; align-items: center; flex-wrap: wrap; margin-bottom: 6px; }
.hit-body { font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; }
.chunk-text { font-size: 12px; }
</style>
