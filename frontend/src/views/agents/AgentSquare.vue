<template>
  <div class="page">
    <div class="page-header">
      <h2>智能体广场</h2>
      <div class="actions">
        <el-input v-model="keyword" placeholder="搜索智能体" style="width: 220px" clearable @input="load" />
        <el-button v-if="userStore.isManager" type="primary" @click="openCreate">新建智能体</el-button>
      </div>
    </div>

    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="a in agents" :key="a.id" :span="8" style="margin-bottom: 16px">
        <el-card shadow="hover" class="agent-card">
          <div class="head">
            <el-avatar :size="44" class="avatar">{{ a.name.slice(0, 1) }}</el-avatar>
            <div class="info">
              <div class="name">
                {{ a.name }}
                <el-tag v-if="userStore.isManager" :type="a.status === 'published' ? 'success' : 'info'" size="small">
                  {{ a.status_label }}
                </el-tag>
              </div>
              <div class="desc">{{ a.description || '暂无简介' }}</div>
            </div>
          </div>
          <div class="kbs">
            <el-tag v-for="k in a.knowledge_base_names" :key="k" size="small" type="success" effect="plain">
              {{ k }}
            </el-tag>
            <el-tag v-if="!a.knowledge_base_names.length" size="small" type="info" effect="plain">未挂知识库</el-tag>
          </div>
          <div class="foot">
            <span class="muted">模型：{{ a.model_name }}</span>
            <div class="btns">
              <template v-if="userStore.isManager">
                <el-button size="small" @click="openEdit(a)">编辑</el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => onMore(cmd, a)">
                  <el-button size="small" type="primary" plain>
                    更多<el-icon><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-if="a.status !== 'published'" command="publish">发布上架</el-dropdown-item>
                      <el-dropdown-item v-else command="unpublish">下架</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
              <el-button type="primary" size="small" @click="$router.push(`/agents/${a.id}/chat`)">开始对话</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && !agents.length" description="暂无智能体" />

    <!-- 新建 / 编辑智能体 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑智能体' : '新建智能体'" width="640" top="5vh">
      <el-form label-width="110">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如 物联网工程导论助教" /></el-form-item>
        <el-form-item label="标识"><el-input v-model="form.code" placeholder="唯一英文标识，如 intro-iot-ta" /></el-form-item>
        <el-form-item label="简介"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="欢迎语"><el-input v-model="form.welcome_message" type="textarea" :rows="2" placeholder="打开对话时显示的欢迎消息" /></el-form-item>
        <el-form-item label="推荐问题">
          <el-input v-model="form.suggestedText" type="textarea" :rows="2" placeholder="一行一个，如：&#10;什么是物联网的三层架构？&#10;RFID 的工作原理是什么？" />
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="form.system_prompt" type="textarea" :rows="4" placeholder="定义智能体的角色与回答规范" />
        </el-form-item>
        <el-form-item label="对话模型">
          <el-select v-model="form.model_id" clearable style="width: 100%">
            <el-option v-for="m in llmOptions" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联知识库">
          <el-select v-model="form.knowledge_base_ids" multiple style="width: 100%">
            <el-option v-for="k in kbs" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="检索条数 top_k">
          <el-input-number v-model="form.top_k" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label="温度"><el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" style="width: 220px" /></el-form-item>
        <el-form-item label="检索优先"><el-switch v-model="form.retrieval_first" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentApi } from '@/api/agents'
import { kbApi } from '@/api/datasets'
import { configApi } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import type { Agent, KnowledgeBase, LlmOption } from '@/types'

const userStore = useUserStore()
const agents = ref<Agent[]>([])
const keyword = ref('')
const loading = ref(false)
const kbs = ref<KnowledgeBase[]>([])
const llmOptions = ref<LlmOption[]>([])

const dialog = ref(false)
const form = reactive<Record<string, any>>({
  id: 0, name: '', code: '', description: '', welcome_message: '', suggestedText: '',
  system_prompt: '', model_id: null as number | null, knowledge_base_ids: [] as number[],
  top_k: 5, temperature: 0.3, retrieval_first: true,
})

async function load() {
  loading.value = true
  try {
    if (userStore.isManager) {
      // 管理员能看到全部（含未发布）。后端 /agents/ 返回数组（非分页结构），做兼容
      const r: any = await agentApi.list({ keyword: keyword.value || undefined })
      agents.value = Array.isArray(r) ? r : (r.items ?? [])
    } else {
      agents.value = (await agentApi.square(keyword.value)).items ?? []
    }
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, {
    id: 0, name: '', code: '', description: '', welcome_message: '', suggestedText: '',
    system_prompt: '', model_id: null, knowledge_base_ids: [], top_k: 5, temperature: 0.3, retrieval_first: true,
  })
  dialog.value = true
}
function openEdit(a: Agent) {
  Object.assign(form, {
    id: a.id, name: a.name, code: a.code, description: a.description, welcome_message: a.welcome_message,
    suggestedText: (a.suggested_questions ?? []).join('\n'), system_prompt: a.system_prompt,
    model_id: a.model_id, knowledge_base_ids: [...a.knowledge_base_ids],
    top_k: a.top_k, temperature: a.temperature, retrieval_first: a.retrieval_first,
  })
  dialog.value = true
}

async function save() {
  const payload = {
    name: form.name,
    ...(form.id ? {} : { code: form.code }),
    description: form.description,
    welcome_message: form.welcome_message,
    suggested_questions: form.suggestedText.split('\n').map((s: string) => s.trim()).filter(Boolean),
    system_prompt: form.system_prompt,
    model_id: form.model_id,
    knowledge_base_ids: form.knowledge_base_ids,
    top_k: form.top_k,
    temperature: form.temperature,
    retrieval_first: form.retrieval_first,
  }
  if (form.id) await agentApi.update(form.id, payload)
  else {
    const created = await agentApi.create(payload)
    ElMessage.success('已创建，发布后出现在广场')
    dialog.value = false
    await agentApi.publish(created.id, 'published').catch(() => {})
    await load()
    return
  }
  ElMessage.success('已保存')
  dialog.value = false
  load()
}

async function onMore(cmd: string, a: Agent) {
  if (cmd === 'publish') {
    await agentApi.publish(a.id, 'published')
    ElMessage.success('已发布')
  } else if (cmd === 'unpublish') {
    await agentApi.publish(a.id, 'draft')
    ElMessage.success('已下架')
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm(`删除智能体「${a.name}」？其会话记录保留。`, '确认', { type: 'warning' })
    await agentApi.remove(a.id)
    ElMessage.success('已删除')
  }
  load()
}

onMounted(async () => {
  load()
  if (userStore.isManager) {
    const [kbRes, llmRes] = await Promise.all([kbApi.list(), configApi.llmOptions().catch(() => ({ items: [] }))])
    kbs.value = kbRes
    llmOptions.value = llmRes.items
  }
})
</script>

<style scoped lang="scss">
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;

  .actions {
    display: flex;
    gap: 10px;
  }
}

.agent-card {
  .head {
    display: flex;
    gap: 12px;

    .avatar {
      background: #409eff;
      font-size: 18px;
      flex-shrink: 0;
    }

    .name {
      font-size: 16px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .desc {
      color: #909399;
      font-size: 13px;
      margin-top: 4px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
  }

  .kbs {
    margin: 14px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .btns {
      display: flex;
      gap: 6px;
      align-items: center;
    }

    .muted {
      color: #909399;
      font-size: 12px;
    }
  }
}
</style>
