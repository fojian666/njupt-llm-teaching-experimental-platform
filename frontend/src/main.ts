import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import {
  ArrowDown,
  ArrowDownBold,
  ArrowRight,
  ChatDotRound,
  CircleCheck,
  CircleCheckFilled,
  CircleClose,
  CircleCloseFilled,
  Collection,
  Cpu,
  Delete,
  DocumentCopy,
  Expand,
  Files,
  Fold,
  FolderOpened,
  Lock,
  MagicStick,
  MoreFilled,
  Promotion,
  Search,
  Setting,
  User,
} from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/index.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

/**
 * 图标按需注册。
 * 原来 `import * as ElementPlusIconsVue` 会把 300+ 个图标全量注册进主包，
 * 而且因为走了命名空间对象，打包器摇不掉。这里只注册实际用到的那些。
 * 新增图标：往下面这张表里加一行（键名 = <el-icon> 里写的名字）。
 */
const icons = {
  Cpu,
  Expand,
  Fold,
  User,
  Lock,
  MagicStick,
  FolderOpened,
  Files,
  Collection,
  DocumentCopy,
  Setting,
  ChatDotRound,
  Search,
  ArrowDown,
  ArrowDownBold,
  ArrowRight,
  CircleCheck,
  CircleCheckFilled,
  CircleClose,
  CircleCloseFilled,
  Delete,
  MoreFilled,
  Promotion,
}

for (const [name, component] of Object.entries(icons)) {
  app.component(name, component)
}

app.mount('#app')
