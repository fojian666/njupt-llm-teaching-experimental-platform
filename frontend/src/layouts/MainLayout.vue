<template>
  <el-container class="layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="aside" :class="{ collapsed }">
      <div class="brand">
        <el-icon :size="collapsed ? 24 : 22"><Cpu /></el-icon>
        <transition name="brand-fade">
          <span v-if="!collapsed" class="brand-name">南京邮电大学物联网学科大模型教学实验平台</span>
        </transition>
      </div>
      <el-menu :default-active="route.path" router class="menu" :collapse="collapsed" :collapse-transition="false">
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
            <transition name="icon-swap" mode="out-in">
              <Expand v-if="collapsed" key="expand" />
              <Fold v-else key="fold" />
            </transition>
          </el-icon>
          <div :key="route.path" class="title">{{ route.meta.title || '' }}</div>
        </div>
        <div class="head-right">
          <!-- 注意：触发元素不要再包 el-tooltip —— dropdown 靠默认插槽的根节点注册事件，
               包一层组件后它认不到实际 DOM 节点，菜单会永远 display:none（点了没反应）。
               需要提示就用原生 title。 -->
          <el-dropdown trigger="click" :show-arrow="false" @command="onThemeCommand">
            <el-icon
              class="theme-btn" :size="17" role="button" tabindex="0" aria-label="切换主题"
              :title="`当前：${currentThemeLabel}，点击切换`"
            >
              <component :is="currentThemeIcon" />
            </el-icon>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="t in THEMES" :key="t.mode" :command="t.mode"
                  :class="{ 'is-current': t.mode === theme }"
                >
                  <el-icon><component :is="t.icon" /></el-icon>
                  <span class="theme-name">{{ t.label }}</span>
                  <span class="theme-hint">{{ t.hint }}</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <!-- 用户菜单：click 触发（hover 路过就弹卡很打扰）+ 右对齐 + 无箭头 + 紧贴 -->
          <el-dropdown
            trigger="click"
            placement="bottom-end"
            :show-arrow="false"
            :popper-options="{ modifiers: [{ name: 'offset', options: { offset: [0, 8] } }] }"
            popper-class="user-menu"
            @visible-change="(v: boolean) => (menuOpen = v)"
            @command="onCommand"
          >
            <span class="user">
              <el-avatar :size="28">{{ userStore.name.slice(0, 1) }}</el-avatar>
              <span class="uname">{{ userStore.name }}</span>
              <el-tag size="small" type="info" effect="plain">{{ userStore.info?.role_label }}</el-tag>
              <el-icon class="caret" :class="{ open: menuOpen }"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main ref="mainEl" class="main">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, watch, type ComponentPublicInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { THEMES, setTheme, theme } from '@/utils/theme'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const collapsed = ref(false)
const menuOpen = ref(false)

/** 切换主题：把点击位置坐标传给动画，圆形扩散才能从图标处展开 */
const currentTheme = computed(() => THEMES.find((t) => t.mode === theme.value) ?? THEMES[0])
const currentThemeLabel = computed(() => currentTheme.value.label)
const currentThemeIcon = computed(() => currentTheme.value.icon)

function onThemeCommand(mode: string) {
  const el = document.querySelector('.theme-btn')?.getBoundingClientRect()
  setTheme(mode as 'light' | 'dark' | 'tech', true,
    el ? { x: el.x + el.width / 2, y: el.y + el.height / 2 } : undefined)
}

/** el-main 是内部滚动的（overflow:auto），window 不滚，所以路由切换要手动复位 */
const mainEl = ref<ComponentPublicInstance | null>(null)
watch(
  () => route.path,
  () => {
    const el = mainEl.value?.$el as HTMLElement | undefined
    el?.scrollTo({ top: 0 })
  },
)

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
  /* 顶栏高度在这一处定死，品牌区、header、内容区高度计算都引用它。
     为什么不用 Element 的 --el-header-height：Element 把它声明在 .el-header 元素自身上，
     外层设的值会被元素自己的声明压掉，实测品牌区 56px 与 header 60px 对不齐。
     之前品牌区写死 56px、header 用默认 60px，侧栏深色时看不出来，改浅色后底边错位很明显。 */
  --shell-head-h: 56px;
}

.aside {
  /* 侧栏改浅色：与内容区、聊天页同一套语言。
     原来的深色 #1f2d3d 是经典后台配色，和右侧浅色工作区一屏之内两种气质。 */
  background: var(--bg-soft);
  border-right: 1px solid var(--line-soft);
  transition: width 0.25s var(--ease);
  overflow: hidden;

  .brand {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    height: var(--shell-head-h);
    padding: 0 14px;
    color: var(--ink-1);
    font-weight: 600;
    border-bottom: 1px solid var(--line-soft);

    .el-icon {
      color: var(--brand);
    }

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
    transition: opacity 0.2s var(--ease), transform 0.2s var(--ease);
  }

  .brand-fade-enter-from,
  .brand-fade-leave-to {
    opacity: 0;
    transform: translateX(-8px);
  }

  /* 收起态：品牌图标要居中，不能再带展开态的左内距。
     左内距 14 + 图标半宽 12 = 26，而 64px 侧栏的中心是 32 —— 差 6px 很明显。 */
  &.collapsed .brand {
    padding: 0;
    justify-content: center;
  }

  .menu {
    border-right: none;

    &:not(.el-menu--collapse) {
      width: 100%;
    }

    /* 菜单项：竖向只留 2px 间隔，横向留白分展开/收起两种处理。
       收起态绝不能加左右外边距 —— Element 是按 64px 整宽算图标居中的，
       加了 margin 图标就会被顶偏。 */
    :deep(.el-menu-item) {
      height: 40px;
      margin: 2px 0;
      border-radius: var(--radius-sm);
      color: var(--ink-2);
      transition: background-color 0.2s var(--ease), color 0.2s var(--ease);

      &:hover {
        background: var(--bg-hover);
        color: var(--ink-1);
      }

      /* 选中态用圆角底 + 品牌色文字，不用左侧色条 */
      &.is-active {
        background: var(--brand-soft);
        color: var(--brand-ink);
        font-weight: 600;
      }
    }

    /* 只有展开态才加左右外边距与左内距 */
    &:not(.el-menu--collapse) :deep(.el-menu-item) {
      margin: 2px 8px;
      padding-left: 14px !important;
    }

    :deep(.el-menu-item span) {
      white-space: nowrap;
    }
  }
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--shell-head-h); /* 显式高度：Element 默认 60px 会与侧栏品牌区差 4px */
  background: var(--bg-card);
  border-bottom: 1px solid var(--line);

  .head-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .head-right {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .theme-btn {
    cursor: pointer;
    color: var(--ink-2);
    transition: color var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease);

    &:hover {
      color: var(--brand);
      transform: rotate(-15deg);
    }
  }

  .theme-name {
    margin-right: 8px;
  }

  .theme-hint {
    color: var(--ink-3);
    font-size: 12px;
  }

  .collapse-btn {
    cursor: pointer;
    color: var(--ink-2);
    transition: color var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease);

    &:hover {
      color: var(--brand);
      transform: scale(1.12);
    }

    /* 展开/收起图标交叉旋转，比硬切换自然 */
    .icon-swap-enter-active,
    .icon-swap-leave-active {
      transition: opacity 0.18s var(--ease), transform 0.18s var(--ease);
    }

    .icon-swap-enter-from {
      opacity: 0;
      transform: rotate(-90deg);
    }

    .icon-swap-leave-to {
      opacity: 0;
      transform: rotate(90deg);
    }
  }

  .title {
    font-size: 16px;
    font-weight: 600;
    animation: fade-up 0.3s var(--ease) both;
  }

  .user {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 5px 10px;
    border-radius: 10px;
    transition: background-color var(--dur-fast) var(--ease);

    &:hover {
      background: var(--bg-hover); /* iOS 系统灰，比 #f5f7fa 清晰一档 */
    }

    &:active {
      background: var(--bg-hover-strong);
    }

    .uname {
      font-size: 14px;
    }

    /* 角标箭头：既是"可点"的提示，展开时翻转给反馈 */
    .caret {
      color: var(--ink-3);
      font-size: 12px;
      transition: transform 0.2s var(--ease);
    }

    .caret.open {
      transform: rotate(180deg);
    }
  }
}

.main {
  padding: 16px; /* 灰底留白，白卡片浮起来；0 会让无卡片包裹的页面贴边 */
  background: var(--bg-page);

  /* 把内容区可用高度算好传下去，页面就不用各自写 calc(100vh - 多少) 了。
     减的是顶栏高度与 .main 上下各 16px 的内边距。 */
  --content-height: calc(100vh - var(--shell-head-h) - 32px);
}
</style>
