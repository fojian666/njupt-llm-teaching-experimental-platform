/**
 * highlight.js 只为主入口提供了类型声明，按需加载的语言模块
 * （highlight.js/lib/languages/*）没有随包发 .d.ts，
 * strict 模式下每个 import 都会报 TS7016。这里补一个通配声明。
 */
declare module 'highlight.js/lib/languages/*' {
  import type { LanguageFn } from 'highlight.js'
  const language: LanguageFn
  export default language
}
