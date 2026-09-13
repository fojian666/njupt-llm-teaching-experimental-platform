<template>
  <div class="page">
    <div class="page-header">
      <h2>数据分类管理</h2>
      <el-button type="primary" @click="openEdit(null)">新建一级分类</el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card shadow="never">
          <el-tree
            ref="treeRef"
            :data="tree"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            default-expand-all
            highlight-current
            @current-change="(n: Category | null) => (current = n)"
          >
            <template #default="{ data }">
              <div class="node">
                <span>
                  <el-icon style="vertical-align: -2px"><FolderOpened /></el-icon>
                  {{ data.name }}
                  <el-tag size="small" type="info" effect="plain" style="margin-left: 6px">{{ data.resource_count }}</el-tag>
                </span>
                <span class="ops" @click.stop>
                  <el-button link size="small" @click="openEdit(data)">编辑</el-button>
                  <el-button link size="small" type="primary" @click="openEdit(null, data.id)">加子级</el-button>
                  <el-button link size="small" type="danger" @click="del(data)">删除</el-button>
                </span>
              </div>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card shadow="never">
          <template #header>分类详情</template>
          <el-descriptions v-if="current" :column="1" border>
            <el-descriptions-item label="分类名称">{{ current.name }}</el-descriptions-item>
            <el-descriptions-item label="完整路径">{{ current.full_path }}</el-descriptions-item>
            <el-descriptions-item label="数据数量">{{ current.resource_count }}</el-descriptions-item>
            <el-descriptions-item label="备注">{{ current.remark || '—' }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="在左侧选择一个分类" :image-size="80" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="dialog" :title="form.id ? '编辑分类' : '新建分类'" width="460px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="上级分类">
          <el-tree-select
            v-model="form.parent_id"
            :data="parentOptions"
            :props="{ label: 'name', children: 'children' }"
            value-key="id"
            check-strictly
            clearable
            placeholder="不选则为一级分类"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="form.name" placeholder="如：02 培养方案" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { categoryApi } from '@/api/datasets'
import type { Category } from '@/types'

const tree = ref<Category[]>([])
const current = ref<Category | null>(null)
const dialog = ref(false)
const saving = ref(false)

const form = ref<Partial<Category>>({ id: undefined, name: '', parent_id: null, sort: 0, remark: '' })
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  name: [
    { required: true, message: '请填写分类名称', trigger: 'blur' },
    { max: 128, message: '名称不能超过 128 个字', trigger: 'blur' },
  ],
}

/** 上级候选：排除自己（避免把分类挂到自己下面形成环） */
const parentOptions = computed(() =>
  stripNode(tree.value, form.value.id),
)

function stripNode(nodes: Category[], excludeId?: number): Category[] {
  if (!excludeId) return nodes
  return nodes
    .filter((n) => n.id !== excludeId)
    .map((n) => ({ ...n, children: stripNode(n.children, excludeId) }))
}

async function load() {
  tree.value = await categoryApi.tree()
}

function openEdit(node: Category | null, parentId?: number) {
  form.value = node
    ? { ...node }
    : { id: undefined, name: '', parent_id: parentId ?? null, sort: 0, remark: '' }
  dialog.value = true
}

async function save() {
  // 之前是手写 if(!name) + toast，这里统一走 el-form 的内联校验（红星 + 就地报错）
  const ok = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload = {
      // validate() 通过后 name 必为非空字符串（规则里 required + max128），
      // 这里的 ! 是给 TS 的窄化提示，不是绕过校验
      name: form.value.name!.trim(),
      code: form.value.code ?? '',
      parent_id: form.value.parent_id || null,
      sort: form.value.sort ?? 0,
      remark: form.value.remark ?? '',
    }
    if (form.value.id) await categoryApi.update(form.value.id, payload)
    else await categoryApi.create(payload)
    ElMessage.success('已保存')
    dialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function del(node: Category) {
  await ElMessageBox.confirm(`确认删除分类「${node.name}」？`, '提示', { type: 'warning' })
  try {
    await categoryApi.remove(node.id)
    ElMessage.success('已删除')
    current.value = null
    await load()
  } catch {
    /* 拦截器已提示（有子级或挂有数据时后端会拒绝） */
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;

  .ops {
    opacity: 0;
    transition: opacity 0.15s;
  }

  &:hover .ops {
    opacity: 1;
  }
}
</style>
