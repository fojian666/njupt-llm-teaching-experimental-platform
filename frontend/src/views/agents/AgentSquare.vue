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
      <el-col v-for="(a, idx) in agents" :key="a.id" :xs="24" :sm="12" :md="8" :lg="6" class="agent-col">
        <div
          class="agent-card"
          :class="{ draft: a.status !== 'published' && userStore.isManager }"
          :style="{ '--i': Math.min(idx, 8), '--g1': gradient(a.id).from, '--g2': gradient(a.id).to }"
          @click="openChat(a)"
        >
          <!-- 管理操作只在悬停时出现，平时让卡片保持干净 -->
          <div v-if="userStore.isManager" class="tools" @click.stop>
            <el-button size="small" text @click="openEdit(a)">编辑</el-button>
            <el-dropdown trigger="click" @command="(cmd: string) => onMore(cmd, a)">
              <el-button size="small" text><el-icon><MoreFilled /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="a.status !== 'published'" command="publish">发布上架</el-dropdown-item>
                  <el-dropdown-item v-else command="unpublish">下架</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div class="avatar">{{ a.name.slice(0, 1) }}</div>

          <div class="name">
            {{ a.name }}
            <span v-if="userStore.isManager" class="status" :class="a.status">
              <i class="dot" />{{ a.status_label }}
            </span>
          </div>
          <div class="desc">{{ a.description || '暂无简介' }}</div>

          <div class="kbs">
            <span v-for="k in a.knowledge_base_names" :key="k" class="kb-chip">{{ k }}</span>
            <span v-if="!a.knowledge_base_names.length" class="kb-chip empty">未挂知识库</span>
          </div>

          <div class="foot">
            <span class="model">{{ a.model_name }}</span>
            <span class="go">开始对话<el-icon><ArrowRight /></el-icon></span>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && !agents.length" description="暂无智能体" />

    <!-- 新建 / 编辑智能体 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑智能体' : '新建智能体'" width="640" top="5vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110">
        <el-form-item label="名称" prop="name"><el-input v-model="form.name" placeholder="如 物联网工程导论助教" maxlength="64" show-word-limit /></el-form-item>
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
        <el-button :disabled="saving" @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentApi } from '@/api/agents'
import { kbApi } from '@/api/datasets'
import { configApi } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { agentGradient as gradient } from '@/utils/agentColor'
import type { FormInstance, FormRules } from 'element-plus'
import type { Agent, KnowledgeBase, LlmOption } from '@/types'

const router = useRouter()
const userStore = useUserStore()

function openChat(a: Agent) {
  router.push(`/agents/${a.id}/chat`)
}

const agents = ref<Agent[]>([])
const keyword = ref('')
const loading = ref(false)
const kbs = ref<KnowledgeBase[]>([])
const llmOptions = ref<LlmOption[]>([])

const dialog = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()
// 必填校验：拦在界面上，而不是等后端 422 再弹一条没头没尾的 toast
const rules: FormRules = {
  name: [
    { required: true, message: '请填写智能体名称', trigger: 'blur' },
    { max: 64, message: '名称不能超过 64 个字', trigger: 'blur' },
  ],
}
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
  if (saving.value) return // 防重复提交：连点两次会建出两个智能体
  const ok = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!ok) return
  saving.value = true
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
  try {
    if (form.id) {
      await agentApi.update(form.id, payload)
    } else {
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
  } finally {
    saving.value = false
  }
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

.agent-col {
  margin-bottom: 16px;
}

/* 卡片：不用 el-card，自己控圆角/阴影/悬停，iOS 那种"应用图标 + 分组卡片"的手感 */
.agent-card {
  position: relative;
  height: 100%;
  padding: 20px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  cursor: pointer;
  transition: transform 0.24s var(--ease), box-shadow 0.24s var(--ease);
  animation: card-in 0.4s var(--ease) backwards;
  animation-delay: calc(var(--i, 0) * 45ms);

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 28px rgba(16, 24, 40, 0.12);
  }

  /* 草稿态整体弱化，一眼能分辨 */
  &.draft {
    background: #fcfcfd;
    box-shadow: inset 0 0 0 1px var(--line-soft), 0 1px 2px rgba(16, 24, 40, 0.03);
  }

  .tools {
    position: absolute;
    top: 12px;
    right: 12px;
    display: flex;
    align-items: center;
    gap: 2px;
    opacity: 0;
    transform: translateY(-4px);
    transition: opacity 0.2s var(--ease), transform 0.2s var(--ease);
  }

  &:hover .tools {
    opacity: 1;
    transform: none;
  }

  /* 头像做成 iOS 应用图标那种 squirle：大圆角 + 双色渐变 + 极淡的内高光 */
  .avatar {
    width: 52px;
    height: 52px;
    border-radius: 16px;
    display: grid;
    place-items: center;
    color: #fff;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 1px;
    background: linear-gradient(145deg, var(--g1, #4facfe), var(--g2, #00c6fb));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 6px 14px rgba(16, 24, 40, 0.14);
  }

  .name {
    margin-top: 14px;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink-1);
    display: flex;
    align-items: center;
    gap: 8px;

    .status {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 400;
      color: var(--ink-3);

      .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #c0c4cc;
      }

      &.published .dot {
        background: #34c759; /* iOS systemGreen */
      }
    }
  }

  .desc {
    margin-top: 6px;
    min-height: 40px;
    color: var(--ink-3);
    font-size: 13px;
    line-height: 1.55;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .kbs {
    margin: 14px 0 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .kb-chip {
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 12px;
    color: var(--brand-ink);
    background: #eef5ff;

    &.empty {
      color: var(--ink-3);
      background: #f2f3f5;
    }
  }

  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 14px;
    border-top: 1px solid var(--line-soft);

    .model {
      font-size: 12px;
      color: var(--ink-3);
    }

    .go {
      display: inline-flex;
      align-items: center;
      gap: 2px;
      font-size: 13px;
      color: var(--brand);
      opacity: 0.72;
      transition: opacity 0.2s var(--ease), transform 0.2s var(--ease);
    }
  }

  &:hover .foot .go {
    opacity: 1;
    transform: translateX(2px);
  }
}
</style>
