<template>
  <div class="login-page">
    <el-card class="card">
      <h2 class="title">物联网学科大模型教学实验平台</h2>
      <p class="sub">基于教材与培养方案的 RAG 知识问答</p>
      <el-form :model="form" size="large" @keyup.enter="submit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" autocomplete="username">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password autocomplete="current-password">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
      <el-alert class="hint" type="info" :closable="false">
        <p>演示账号：admin / admin123（管理员）</p>
        <p>teacher / teacher123（教师）　student / student123（学生）</p>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = reactive({ username: 'admin', password: 'admin123' })
const loading = ref(false)

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    router.push((route.query.next as string) || '/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: linear-gradient(135deg, #1f2d3d 0%, #2b4a6f 100%);
}

.card {
  width: 380px;
  padding: 8px 12px;

  .title {
    margin: 8px 0 4px;
    text-align: center;
    font-size: 19px;
  }

  .sub {
    margin: 0 0 20px;
    text-align: center;
    color: #909399;
    font-size: 13px;
  }

  .hint {
    margin-top: 16px;

    p {
      margin: 2px 0;
      font-size: 12px;
      line-height: 1.5;
    }
  }
}
</style>
