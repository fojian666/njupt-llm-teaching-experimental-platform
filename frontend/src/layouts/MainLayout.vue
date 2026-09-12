<template>
  <el-container class="layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="aside">
      <div class="brand">
        <el-icon :size="collapsed ? 24 : 22"><Cpu /></el-icon>
        <transition name="brand-fade">
          <span v-if="!collapsed" class="brand-name">南京邮电大学物联网学科大模型教学实验平台</span>
        </transition>
      </div>
      <el-menu :default-active="route.path" router class="menu" :collapse="collapsed" :collapse-transition="false" background-color="#1f2d3d" text-color="#bfcbd9" active-text-color="#409EFF">
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="head-left">
          <el-icon class="collapse-btn" :size="18" @click="collapsed = !collapsed">
            <Expand v-if="collapsed" />
            <Fold v-else />
          </el-icon>
          <div class="title">{{ route.meta.title || '' }}</div>
        </div>
        <el-dropdown @command="onCommand">
          <span class="user">
            <el-avatar :size="28">{{ userStore.name.slice(0, 1) }}</el-avatar>
            <span class="uname">{{ userStore.name }}</span>
            <el-tag size="small" type="info">{{ userStore.info?.role_label }}</el-tag>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const collapsed = ref(false)

/** 学生只看得到智能体广场，管理端入口对他隐藏 */
const menus = computed(() =>
  [
    { path: '/agents', title: '智能体广场', icon: 'MagicStick' },
    { path: '/datasets/categories', title: '数据分类管理', icon: 'FolderOpened', manager: true },
    { path: '/datasets/resources', title: '数据资源', icon: 'Files', manager: true },
    { path: '/knowledge', title: '知识管理', icon: 'Collection', manager: true },
    { path: '/configs', title: '配置中心', icon: 'Setting', manager: true },
    { path: '/audit/records', title: '问答记录', icon: 'ChatDotRound', manager: true },
  ].filter((m) => !m.manager || userStore.isManager),
)

async function onCommand(cmd: string) {
  if (cmd === 'logout') {
    await userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped lang="scss">
.layout {
  height: 100%;
}

.aside {
  background: #1f2d3d;
  transition: width 0.25s ease;
  overflow: hidden;

  .brand {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    height: 56px;
    padding: 0 14px;
    color: #fff;
    font-weight: 600;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);

    /* 绝对定位 + 固定宽：收起动画时文字整体被裁切淡出，而不是被挤压重排 */
    .brand-name {
      position: absolute;
      left: 44px;
      top: 50%;
      transform: translateY(-50%);
      width: 160px;
      font-size: 13px;
      line-height: 1.45;
    }
  }

  .brand-fade-enter-active,
  .brand-fade-leave-active {
    transition: opacity 0.2s ease, transform 0.2s ease;
  }

  .brand-fade-enter-from,
  .brand-fade-leave-to {
    opacity: 0;
    transform: translateX(-8px);
  }

  .menu {
    border-right: none;

    &:not(.el-menu--collapse) {
      width: 100%;
    }

    /* 菜单文字强制单行：宽度动画期间只被裁切，不发生换行挤压 */
    :deep(.el-menu-item span) {
      white-space: nowrap;
    }
  }
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;

  .head-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .collapse-btn {
    cursor: pointer;
    color: #606266;

    &:hover {
      color: #409eff;
    }
  }

  .title {
    font-size: 16px;
    font-weight: 600;
  }

  .user {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;

    .uname {
      font-size: 14px;
    }
  }
}

.main {
  padding: 16px; /* 灰底留白，白卡片浮起来；0 会让无卡片包裹的页面贴边 */
  background: #f5f7fa;
}
</style>
