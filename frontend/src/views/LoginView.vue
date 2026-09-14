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
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  overflow: hidden;
  background: linear-gradient(135deg, #1f2d3d 0%, #2b4a6f 55%, #1f2d3d 100%);
  background-size: 220% 220%;
  animation: bg-pan 24s ease-in-out infinite alternate;

  /* 右上角一团柔光，给纯色背景一点纵深 */
  &::before {
    content: '';
    position: absolute;
    top: -160px;
    right: -120px;
    width: 520px;
    height: 520px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(10, 132, 255, 0.35) 0%, rgba(10, 132, 255, 0) 70%);
    pointer-events: none;
  }
}

@keyframes bg-pan {
  from {
    background-position: 0% 50%;
  }
  to {
    background-position: 100% 50%;
  }
}

.card {
  position: relative;
  width: 380px;
  padding: 8px 12px;
  border: none;
  /* el-card 的阴影走的是 CSS 变量，直接覆盖变量比硬写 box-shadow 更稳（不会被 .is-always-shadow 盖掉） */
  --el-box-shadow-light: 0 18px 48px rgba(10, 22, 36, 0.38);
  animation: card-in 0.5s var(--ease) both;

  .title {
    margin: 8px 0 4px;
    text-align: center;
    font-size: 19px;
    animation: fade-up 0.5s var(--ease) 0.08s both;
  }

  .sub {
    margin: 0 0 20px;
    text-align: center;
    color: var(--ink-3);
    font-size: 13px;
    animation: fade-up 0.5s var(--ease) 0.14s both;
  }

  :deep(.el-form) {
    animation: fade-up 0.5s var(--ease) 0.2s both;
  }

  .hint {
    margin-top: 16px;
    animation: fade-up 0.5s var(--ease) 0.26s both;

    p {
      margin: 2px 0;
      font-size: 12px;
      line-height: 1.5;
    }
  }
}
</style>
