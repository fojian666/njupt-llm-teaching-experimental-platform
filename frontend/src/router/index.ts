import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      redirect: '/agents',
      children: [
        { path: 'agents', name: 'agent-square', component: () => import('@/views/agents/AgentSquare.vue'), meta: { title: '智能体广场', icon: 'MagicStick' } },
        { path: 'agents/:id/chat', name: 'agent-chat', component: () => import('@/views/agents/ChatView.vue'), meta: { title: '对话', hidden: true } },
        { path: 'datasets/categories', name: 'ds-categories', component: () => import('@/views/datasets/CategoryView.vue'), meta: { title: '数据分类管理', icon: 'FolderOpened', manager: true } },
        { path: 'datasets/resources', name: 'ds-resources', component: () => import('@/views/datasets/ResourceView.vue'), meta: { title: '数据资源', icon: 'Files', manager: true } },
        { path: 'knowledge', name: 'knowledge', component: () => import('@/views/knowledge/KnowledgeView.vue'), meta: { title: '知识管理', icon: 'Collection', manager: true } },
        { path: 'configs', name: 'configs', component: () => import('@/views/configs/ConfigView.vue'), meta: { title: '配置中心', icon: 'Setting', manager: true } },
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
    return { name: 'agent-square' }
  }
  return true
})

export default router
