/**
 * 主题切换：两套主题，全部由 CSS 变量承担，组件侧不需要知道当前是哪套。
 *
 *   light  亮色（默认）
 *   tech   科技风，深海军蓝 + 蓝青双色 + 玻璃质感（与登录页同一套语言）
 *
 * 首屏防白闪：index.html 里有一段内联脚本，在样式加载前就把类名写上去；
 * 这里的 initTheme 负责后续同步与切换。
 */
import { ref } from 'vue'

export type ThemeMode = 'light' | 'tech'

const STORAGE_KEY = 'iot-edu-theme'

/** 两套主题的展示信息。切换入口按这张表渲染，新增主题只改这里。 */
export const THEMES: { mode: ThemeMode; label: string; icon: string; hint: string }[] = [
  { mode: 'light', label: '亮色', icon: 'Sunny', hint: '白底浅灰，适合白天' },
  { mode: 'tech', label: '科技风', icon: 'MagicStick', hint: '深蓝玻璃质感，投屏演示更抓眼' },
]

/** 当前主题。响应式，供界面显示图标用。 */
export const theme = ref<ThemeMode>('light')

// 所有主题可能挂上的类，切换前先全部摘掉。
// tech 会同时挂 dark + tech，所以 dark 必须在这里，否则从 tech 切回亮色会残留 dark。
const ALL_CLASSES: string[] = ['dark', 'tech']

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** 读取已保存的偏好；没有保存过就跟随系统。 */
export function resolveInitialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    // 历史兼容：旧版纯黑 dark 已废弃，统一迁移到科技风
    if (saved === 'dark') return 'tech'
    if (saved === 'light' || saved === 'tech') return saved
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略即可 */
  }
  return systemPrefersDark() ? 'tech' : 'light'
}

/**
 * 科技风要**同时**挂 dark 与 tech 两个类。
 *
 * 原因：Element Plus 的组件级暗色支持（弹窗、下拉、选择器、分页、树、空态……
 * 几百个变量）只认 `html.dark`，那套变量是官方维护、覆盖最完整的。
 * 只挂 tech 的话只能靠手写覆盖，必然漏 —— 表现就是"页面是深色，弹出来一片白"。
 * 所以：dark 负责把 Element 组件整体切暗，tech 在其上做品牌与玻璃质感的着色。
 * CSS 顺序上我们的样式在 Element 之后加载，同优先级下 tech 的令牌会胜出。
 */
function modeClasses(mode: ThemeMode): string[] {
  if (mode === 'tech') return ['dark', 'tech']
  return []
}

function apply(mode: ThemeMode) {
  const root = document.documentElement
  root.classList.remove(...ALL_CLASSES)
  for (const cls of modeClasses(mode)) root.classList.add(cls)
  // 让原生控件（滚动条、表单、日期选择器）也切到对应配色
  root.style.colorScheme = mode === 'light' ? 'light' : 'dark'
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

/** 按顺序切到下一套主题，供快捷键或单按钮使用。 */
export function cycleTheme(origin?: { x: number; y: number }) {
  const idx = THEMES.findIndex((t) => t.mode === theme.value)
  const next = THEMES[(idx + 1) % THEMES.length]
  setTheme(next.mode, true, origin)
}

/** 应用启动时调用一次，让响应式状态与 <html> 上的类名一致。 */
export function initTheme() {
  apply(resolveInitialTheme())
}
