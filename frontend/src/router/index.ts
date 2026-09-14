import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

/**
 * 路由命名约定
 * 1. path：`/<模块>` 或 `/<模块>/<页面>`，模块名用复数、全小写、不用缩写
 * 2. name：与 path 同构的 kebab-case，`<模块>-<页面>`；模块下唯一页面可省页面段
 * 3. 详情类页面挂在所属模块下并带参数，meta.hidden 不进左侧菜单
 * 4. 菜单由 MainLayout 按 path 生成，改名不影响导航
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      redirect: '/agents',
      children: [
        { path: 'agents', name: 'agents-square', component: () => import('@/views/agents/AgentSquare.vue'), meta: { title: '智能体广场', icon: 'MagicStick' } },
        { path: 'agents/:id/chat', name: 'agents-chat', component: () => import('@/views/agents/ChatView.vue'), meta: { title: '对话', hidden: true } },
        { path: 'datasets/categories', name: 'datasets-categories', component: () => import('@/views/datasets/CategoryView.vue'), meta: { title: '数据分类管理', icon: 'FolderOpened', manager: true } },
        { path: 'datasets/resources', name: 'datasets-resources', component: () => import('@/views/datasets/ResourceView.vue'), meta: { title: '数据资源', icon: 'Files', manager: true } },
        { path: 'knowledge', name: 'knowledge-bases', component: () => import('@/views/knowledge/KnowledgeView.vue'), meta: { title: '知识管理', icon: 'Collection', manager: true } },
        { path: 'configs', name: 'configs-center', component: () => import('@/views/configs/ConfigView.vue'), meta: { title: '配置中心', icon: 'Setting', manager: true } },
        { path: 'audit/records', name: 'audit-records', component: () => import('@/views/audit/RecordView.vue'), meta: { title: '问答记录', icon: 'ChatDotRound', manager: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const user = useUserStore()
  if (to.meta.public) return true

  if (!user.loaded) await user.load()
  if (!user.isLoggedIn) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.meta.manager && !user.isManager) {
    ElMessage.warning('当前账号没有管理权限')
    return { name: 'agents-square' }
  }
  return true
})

export default router
