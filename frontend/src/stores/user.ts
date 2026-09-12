import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import type { UserInfo } from '@/types'

/** 用户会话状态。角色决定菜单可见性与操作权限。 */
export const useUserStore = defineStore('user', {
  state: () => ({
    info: null as UserInfo | null,
    loaded: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.info,
    isManager: (s) => !!s.info && (s.info.is_manager || s.info.role === 'teacher'),
    name: (s) => s.info?.name ?? '',
  },
  actions: {
    async load() {
      try {
        this.info = await authApi.me()
      } catch {
        this.info = null
      } finally {
        this.loaded = true
      }
    },
    async login(username: string, password: string) {
      this.info = await authApi.login(username, password)
      this.loaded = true
    },
    async logout() {
      await authApi.logout()
      this.info = null
    },
  },
})
