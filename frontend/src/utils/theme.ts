/**
 * 主题切换。
 *
 * 做法：<html> 上加/去 dark 类，配色全部由 CSS 变量（styles/index.scss）承担，
 * 组件侧不需要知道当前是什么主题。
 *
 * 首屏防白闪：index.html 里有一段内联脚本，在样式加载前就把类名写上去；
 * 这里的 initTheme 负责后续同步与提供切换 API。
 */
import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'iot-edu-theme'

/** 当前主题。响应式，供界面显示图标用。 */
export const theme = ref<ThemeMode>('light')

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** 读取已保存的偏好；没有保存过就跟随系统。 */
export function resolveInitialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略即可 */
  }
  return systemPrefersDark() ? 'dark' : 'light'
}

function apply(mode: ThemeMode) {
  const root = document.documentElement
  root.classList.toggle('dark', mode === 'dark')
  // 让原生控件（滚动条、表单、日期选择器）也切到对应配色
  root.style.colorScheme = mode
  theme.value = mode
}

export function setTheme(mode: ThemeMode, persist = true) {
  apply(mode)
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, mode)
    } catch {
      /* 存不了就算了，本次会话仍然生效 */
    }
  }
}

export function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}

/** 应用启动时调用一次，让响应式状态与 <html> 上的类名一致。 */
export function initTheme() {
  apply(resolveInitialTheme())
}
