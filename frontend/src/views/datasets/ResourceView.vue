<template>
  <div class="page">
    <div class="page-header">
      <h2>数据资源</h2>
      <div class="actions">
        <el-upload :show-file-list="false" :before-upload="doUpload" accept=".docx,.doc,.pdf,.txt,.md,.epub,.xlsx,.xls,.csv,.html">
          <el-button type="primary" :loading="uploading">上传数据</el-button>
        </el-upload>
      </div>
    </div>

    <el-card shadow="never" class="filter">
      <el-form inline>
        <el-form-item label="分类">
          <!-- value-key 不能省：tree-select 取值的字段是 props.nodeKey || props.valueKey || 'value'，
               分类数据的唯一标识叫 id，不指定就会取到 undefined，筛选静默失效 -->
          <el-tree-select
            v-model="filter.category_id"
            :data="tree"
            :props="{ label: 'name', children: 'children' }"
            value-key="id"
            check-strictly clearable placeholder="全部分类" style="width: 200px"
            @change="load(1)"
          />
        </el-form-item>
        <el-form-item label="解析状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 140px" @change="load(1)">
            <el-option v-for="(l, v) in STATUS" :key="v" :label="l" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="filter.keyword" placeholder="名称 / 来源说明" clearable style="width: 200px" @keyup.enter="load(1)" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" @selection-change="(s: DataResource[]) => (selected = s)">
        <el-table-column type="selection" width="44" />
        <el-table-column prop="name" label="数据名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="category_path" label="数据分类" min-width="150" show-overflow-tooltip />
        <el-table-column prop="upload_method_label" label="上传方式" width="100" />
        <el-table-column prop="file_format" label="格式" width="70" />
        <el-table-column label="标签" min-width="130">
          <template #default="{ row }">
            <el-tag v-for="t in row.tags" :key="t" size="small" effect="plain" style="margin-right: 4px">{{ t }}</el-tag>
            <span v-if="!row.tags.length" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="解析状态" width="150">
          <template #default="{ row }">
            <el-tooltip :content="row.parse_message" placement="top" :disabled="!row.parse_message">
              <el-tag :type="statusType(row.parse_status)" size="small">{{ row.parse_status_label }}</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="char_count" label="字符数" width="90" />
        <el-table-column prop="created_at" label="上传时间" width="150" />
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" :disabled="row.parse_status === 'parsing'" @click="parse(row as DataResource)">解析</el-button>
            <el-button link size="small" @click="preview(row as DataResource)">详情</el-button>
            <el-button link size="small" @click="openEdit(row as DataResource)">编辑</el-button>
            <el-button link size="small" type="danger" @click="del(row as DataResource)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <span class="muted">已选 {{ selected.length }} 项</span>
        <el-button size="small" :disabled="!selected.length" @click="batchDel">批量删除</el-button>
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load()"
        />
      </div>
    </el-card>

    <!-- 数据详情：正文预览 + 已入库的知识库 -->
    <el-drawer v-model="drawer" :title="detail?.name" size="55%">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="分类">{{ detail.category_path }}</el-descriptions-item>
          <el-descriptions-item label="格式">{{ detail.file_format }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ detail.file_size_label }}</el-descriptions-item>
          <el-descriptions-item label="字符数">{{ detail.char_count }}</el-descriptions-item>
          <el-descriptions-item label="解析状态" :span="2">{{ detail.parse_status_label }} · {{ detail.parse_message }}</el-descriptions-item>
          <el-descriptions-item label="已入知识库" :span="2">
            <el-tag v-for="n in detail.in_knowledge_bases" :key="n" size="small" type="success" style="margin-right: 6px">{{ n }}</el-tag>
            <span v-if="!detail.in_knowledge_bases.length" class="muted">未导入</span>
          </el-descriptions-item>
        </el-descriptions>
        <h4 style="margin: 16px 0 8px">正文预览</h4>
        <pre class="preview">{{ detail.content_preview || '（尚未解析出正文）' }}</pre>
      </template>
    </el-drawer>

    <!-- 编辑元数据：名称 / 分类 / 标签 / 来源说明（解析结果不变） -->
    <el-dialog v-model="editDialog" title="编辑数据" width="520">
      <el-form label-width="90">
        <el-form-item label="名称"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="分类">
          <!-- 同样要 value-key（见上方筛选处说明），否则编辑里选的分类存不进去 -->
          <el-tree-select
            v-model="editForm.category_id" :data="tree" clearable check-strictly
            :props="{ label: 'name', children: 'children' }" value-key="id"
            placeholder="不修改则留空" style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="editForm.tags" multiple filterable allow-create default-first-option placeholder="选择或输入新标签" style="width: 100%">
            <el-option v-for="t in tagOptions" :key="t" :label="t" :value="t" />
          </el-select>
          <div class="muted" style="font-size: 12px; line-height: 1.6">可直接输入新标签名，回车创建</div>
        </el-form-item>
        <el-form-item label="来源说明"><el-input v-model="editForm.source_note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { categoryApi, resourceApi, tagApi } from '@/api/datasets'
import type { Category, DataResource } from '@/types'

const STATUS: Record<string, string> = {
  not_parsed: '未解析', pending: '待解析', parsing: '解析中', success: '解析成功', failed: '解析失败',
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
function statusType(s: string): TagType {
  return ({ success: 'success', failed: 'danger', parsing: 'warning', pending: 'info', not_parsed: 'info' } as Record<string, TagType>)[s] ?? 'info'
}

const tree = ref<Category[]>([])
const rows = ref<DataResource[]>([])
const selected = ref<DataResource[]>([])
const detail = ref<DataResource | null>(null)
const drawer = ref(false)
const loading = ref(false)
const uploading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 20

const filter = reactive({ category_id: undefined as number | undefined, status: '', keyword: '' })

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const res = await resourceApi.list({ ...filter, page: p, page_size: pageSize })
    rows.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function reset() {
  filter.category_id = undefined
  filter.status = ''
  filter.keyword = ''
  load(1)
}

async function doUpload(file: File) {
  uploading.value = true
  try {
    await resourceApi.upload(file, { name: file.name })
    ElMessage.success('上传成功')
    await load(1)
  } finally {
    uploading.value = false
  }
  return false // 阻止 el-upload 的默认请求，由我们自己发
}

async function parse(row: DataResource) {
  await resourceApi.parse(row.id)
  ElMessage.success('已开始解析，稍后刷新查看状态')
  setTimeout(() => load(), 1500)
}

async function preview(row: DataResource) {
  detail.value = await resourceApi.get(row.id)
  drawer.value = true
}

async function del(row: DataResource) {
  await ElMessageBox.confirm(`确认删除「${row.name}」？`, '提示', { type: 'warning' })
  try {
    await resourceApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 已被知识库引用时后端会拒绝并提示 */
  }
}

async function batchDel() {
  await ElMessageBox.confirm(`确认删除选中的 ${selected.value.length} 条数据？`, '提示', { type: 'warning' })
  await resourceApi.batchRemove(selected.value.map((r) => r.id))
  ElMessage.success('已删除')
  await load()
}

// ---------------- 编辑元数据 ----------------
const editDialog = ref(false)
const editId = ref(0)
const tagOptions = ref<string[]>([])
const editForm = reactive({
  name: '', category_id: undefined as number | null | undefined, tags: [] as string[], source_note: '',
})

async function openEdit(row: DataResource) {
  editId.value = row.id
  Object.assign(editForm, {
    name: row.name,
    category_id: row.category_id,
    tags: [...(row.tags ?? [])],
    source_note: row.source_note ?? '',
  })
  if (!tagOptions.value.length) {
    try {
      tagOptions.value = (await tagApi.list()).map((t) => t.name)
    } catch { /* 学生无权限时忽略 */ }
  }
  editDialog.value = true
}

async function saveEdit() {
  const payload: Record<string, unknown> = {
    name: editForm.name,
    tags: editForm.tags,
    source_note: editForm.source_note,
  }
  // 分类留空 = 不修改（避免把已有分类误清掉）
  if (editForm.category_id != null) payload.category_id = editForm.category_id
  await resourceApi.update(editId.value, payload)
  ElMessage.success('已保存')
  editDialog.value = false
  // 新输入的标签补充进候选
  for (const t of editForm.tags) if (!tagOptions.value.includes(t)) tagOptions.value.push(t)
  load()
}

onMounted(async () => {
  tree.value = await categoryApi.tree()
  await load(1)
})
</script>

<style scoped lang="scss">
.filter {
  margin-bottom: 16px;

  :deep(.el-form-item) {
    margin-bottom: 0;
  }
}

.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 14px;
}

.preview {
  max-height: 55vh;
  overflow: auto;
  padding: 12px;
  background: #fafbfc;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
}
</style>
