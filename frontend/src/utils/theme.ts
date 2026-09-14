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

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** 不支持 View Transitions 时的兜底：临时打开全局颜色过渡，结束后摘掉。
 *  不常驻是刻意的 —— 常驻会把 hover、弹窗等所有颜色变化都拖成慢动作。 */
function withCssFallback(fn: () => void) {
  const root = document.documentElement
  root.classList.add('theme-transition')
  fn()
  window.setTimeout(() => root.classList.remove('theme-transition'), 420)
}

/**
 * 切换主题。
 *
 * 动画优先用 View Transitions：以点击位置为圆心做圆形扩散；
 * 浏览器不支持就退化成全局颜色渐变，用户偏好减少动效则直接切。
 */
export function setTheme(mode: ThemeMode, persist = true, origin?: { x: number; y: number }) {
  const root = document.documentElement
  const commit = () => {
    apply(mode)
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, mode)
      } catch {
        /* 存不了就算了，本次会话仍然生效 */
      }
    }
  }

  // 用户明确要求减少动效：直接切，连颜色过渡都不要
  if (prefersReducedMotion()) {
    commit()
    return
  }

  const startViewTransition = (
    document as Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } }
  ).startViewTransition

  if (typeof startViewTransition !== 'function') {
    withCssFallback(commit)
    return
  }

  // 圆心取点击位置；拿不到就取视口中心
  const x = origin?.x ?? window.innerWidth / 2
  const y = origin?.y ?? window.innerHeight / 2
  root.style.setProperty('--theme-x', `${x}px`)
  root.style.setProperty('--theme-y', `${y}px`)

  startViewTransition.call(document, commit)
}

export function toggleTheme(origin?: { x: number; y: number }) {
  setTheme(theme.value === 'dark' ? 'light' : 'dark', true, origin)
}

/** 应用启动时调用一次，让响应式状态与 <html> 上的类名一致。 */
export function initTheme() {
  apply(resolveInitialTheme())
}
