<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { providerApi, modelApi, statusApi } from '@/api/configs'
import type { ModelProvider, ModelConfig } from '@/types'

const providers = ref<ModelProvider[]>([])
const models = ref<ModelConfig[]>([])
const status = ref<Record<string, any> | null>(null)
const loading = ref(false)

const modelsByProvider = computed(() => {
  const map = new Map<number, ModelConfig[]>()
  for (const m of models.value) {
    const arr = map.get(m.provider_id) ?? []
    arr.push(m)
    map.set(m.provider_id, arr)
  }
  return map
})

// ---------------- 供应商 ----------------
const providerDialog = ref(false)
const providerForm = reactive({
  id: 0, name: '', code: '', base_url: '', api_key: '', is_active: true, sort: 0, remark: '',
})
function openCreateProvider() {
  Object.assign(providerForm, { id: 0, name: '', code: '', base_url: 'https://api.openai.com/v1', api_key: '', is_active: true, sort: 0, remark: '' })
  providerDialog.value = true
}
function openEditProvider(p: ModelProvider) {
  Object.assign(providerForm, { id: p.id, name: p.name, code: p.code, base_url: p.base_url, api_key: '', is_active: p.is_active, sort: p.sort, remark: p.remark })
  providerDialog.value = true
}
async function saveProvider() {
  const payload = { ...providerForm }
  if (!providerForm.id) delete (payload as any).id
  if (providerForm.id) await providerApi.update(providerForm.id, payload)
  else await providerApi.create(payload)
  ElMessage.success('已保存')
  providerDialog.value = false
  load()
}
async function removeProvider(p: ModelProvider) {
  await ElMessageBox.confirm(`删除供应商「${p.name}」？（其下有 ${p.model_count} 个模型时不允许删除）`, '确认', { type: 'warning' })
  await providerApi.remove(p.id)
  load()
}

// ---------------- 模型 ----------------
const modelDialog = ref(false)
const modelForm = reactive({
  id: 0, provider_id: 0, name: '', model_id: '', kind: 'llm',
  dimension: null as number | null, max_tokens: 4096, temperature: 0.3,
  is_default: false, is_active: true, sort: 0,
})
function openCreateModel(p: ModelProvider) {
  Object.assign(modelForm, { id: 0, provider_id: p.id, name: '', model_id: '', kind: 'llm', dimension: null, max_tokens: 4096, temperature: 0.3, is_default: false, is_active: true, sort: 0 })
  modelDialog.value = true
}
function openEditModel(m: ModelConfig) {
  Object.assign(modelForm, {
    id: m.id, provider_id: m.provider_id, name: m.name, model_id: m.model_id, kind: m.kind,
    dimension: m.dimension, max_tokens: m.max_tokens, temperature: m.temperature,
    is_default: m.is_default, is_active: m.is_active, sort: m.sort,
  })
  modelDialog.value = true
}
async function saveModel() {
  const payload = { ...modelForm }
  if (!modelForm.id) delete (payload as any).id
  if (modelForm.id) await modelApi.update(modelForm.id, payload)
  else await modelApi.create(payload)
  ElMessage.success('已保存')
  modelDialog.value = false
  load()
}
async function removeModel(m: ModelConfig) {
  await ElMessageBox.confirm(`删除模型「${m.name}」？`, '确认', { type: 'warning' })
  await modelApi.remove(m.id)
  load()
}

const kindLabel: Record<string, string> = { llm: '大语言模型', embedding: '向量模型', rerank: '重排模型' }
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'
const kindTag: Record<string, TagType> = { llm: 'primary', embedding: 'success', rerank: 'warning' }

async function load() {
  loading.value = true
  try {
    const [p, m, s] = await Promise.all([
      providerApi.list(),
      modelApi.list(),
      statusApi.status().catch(() => null),
    ])
    providers.value = p
    models.value = m
    status.value = s
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <!-- 模型可用性体检 -->
    <el-card v-if="status" shadow="never" class="mb16">
      <el-row :gutter="16">
        <el-col :span="12">
          <div class="status-item">
            <b>对话模型</b>
            <span class="ml8">{{ status.llm.model }}</span>
            <el-tag size="small" class="ml8">{{ status.llm.source }}</el-tag>
            <el-tag :type="status.llm.has_key ? 'success' : 'danger'" size="small" class="ml8">
              {{ status.llm.has_key ? 'Key 已配置' : '缺少 Key' }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="12">
          <div class="status-item">
            <b>向量模型</b>
            <span class="ml8">{{ status.embedding.model }}</span>
            <el-tag size="small" class="ml8">{{ status.embedding.source }}</el-tag>
            <el-tag :type="status.embedding.has_key ? 'success' : 'danger'" size="small" class="ml8">
              {{ status.embedding.has_key ? 'Key 已配置' : '缺少 Key' }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>模型供应商（OpenAI 兼容协议）</span>
          <el-button type="primary" @click="openCreateProvider">新建供应商</el-button>
        </div>
      </template>

      <el-empty v-if="!providers.length" description="暂无供应商，点击右上角新建" />

      <div v-for="p in providers" :key="p.id" class="provider-block">
        <div class="provider-head">
          <div class="provider-title">
            <el-tag size="small">{{ p.code }}</el-tag>
            <b class="ml8">{{ p.name }}</b>
            <span class="muted ml8">{{ p.base_url }}</span>
            <el-tag :type="p.has_key ? 'success' : 'info'" size="small" class="ml8">
              {{ p.has_key ? p.key_hint : '未配置 Key' }}
            </el-tag>
            <el-tag v-if="!p.is_active" type="danger" size="small" class="ml8">已停用</el-tag>
          </div>
          <div>
            <el-button size="small" @click="openCreateModel(p)">+ 添加模型</el-button>
            <el-button size="small" @click="openEditProvider(p)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="removeProvider(p)">删除</el-button>
          </div>
        </div>

        <el-table :data="modelsByProvider.get(p.id) ?? []" size="small" border :show-header="(modelsByProvider.get(p.id) ?? []).length > 0">
          <el-table-column prop="name" label="名称" min-width="130" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              <el-tag :type="kindTag[row.kind]" size="small">{{ kindLabel[row.kind] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="model_id" label="模型 ID" min-width="170" />
          <el-table-column label="默认" width="70">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" type="warning" size="small">默认</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="维度" width="70">
            <template #default="{ row }">{{ row.dimension ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="max_tokens" label="max_tokens" width="100" />
          <el-table-column prop="temperature" label="温度" width="70" />
          <el-table-column label="启用" width="70">
            <template #default="{ row }">
              <el-switch v-model="row.is_active" size="small" disabled />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openEditModel(row as ModelConfig)">编辑</el-button>
              <el-button size="small" link type="danger" @click="removeModel(row as ModelConfig)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-dialog v-model="providerDialog" :title="providerForm.id ? '编辑供应商' : '新建供应商'" width="520">
      <el-form label-width="90">
        <el-form-item label="名称"><el-input v-model="providerForm.name" placeholder="如 DeepSeek" /></el-form-item>
        <el-form-item label="标识"><el-input v-model="providerForm.code" placeholder="如 deepseek（唯一，建好后不可改）" /></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="providerForm.base_url" placeholder="https://api.deepseek.com/v1" /></el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="providerForm.api_key" type="password" show-password :placeholder="providerForm.id ? '留空则不修改' : 'sk-...'" />
        </el-form-item>
        <el-form-item label="排序"><el-input-number v-model="providerForm.sort" :min="0" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="providerForm.remark" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialog = false">取消</el-button>
        <el-button type="primary" @click="saveProvider">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="modelDialog" :title="modelForm.id ? '编辑模型' : '添加模型'" width="560">
      <el-form label-width="100">
        <el-form-item label="名称"><el-input v-model="modelForm.name" /></el-form-item>
        <el-form-item label="模型 ID"><el-input v-model="modelForm.model_id" placeholder="如 deepseek-chat / text-embedding-3-small" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="modelForm.kind">
            <el-radio-button value="llm">大语言模型</el-radio-button>
            <el-radio-button value="embedding">向量模型</el-radio-button>
            <el-radio-button value="rerank">重排模型</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="modelForm.kind !== 'llm'" label="向量维度">
          <el-input-number v-model="modelForm.dimension" :min="0" />
        </el-form-item>
        <el-form-item label="max_tokens"><el-input-number v-model="modelForm.max_tokens" :min="256" :step="256" /></el-form-item>
        <el-form-item label="温度"><el-slider v-model="modelForm.temperature" :min="0" :max="2" :step="0.1" style="width: 200px" /></el-form-item>
        <el-form-item label="设为默认"><el-switch v-model="modelForm.is_default" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="modelForm.is_active" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialog = false">取消</el-button>
        <el-button type="primary" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mb16 { margin-bottom: 16px; }
.ml8 { margin-left: 8px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.provider-block { padding: 12px 0; border-bottom: 1px dashed var(--el-border-color); }
.provider-block:last-of-type { border-bottom: none; }
.provider-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.provider-title { display: flex; align-items: center; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.status-item { display: flex; align-items: center; }
</style>
