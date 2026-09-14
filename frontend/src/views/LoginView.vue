<template>
  <div class="login-page" @mousemove="onMouseMove" @mouseleave="onMouseLeave">
    <!-- 背景：粒子互联网络（设备互联的隐喻）+ 两团漂浮光晕 + 渐隐网格 -->
    <canvas ref="canvasEl" class="bg-canvas" aria-hidden="true"></canvas>
    <div class="glow glow-a" aria-hidden="true"></div>
    <div class="glow glow-b" aria-hidden="true"></div>
    <div class="grid" aria-hidden="true"></div>

    <div class="stage" :style="parallax">
      <!-- 徽标：玻璃底 + 呼吸光环 + 旋转流光描边 -->
      <div class="badge">
        <span class="ring" aria-hidden="true"></span>
        <span class="core"><el-icon :size="26"><Cpu /></el-icon></span>
      </div>

      <!-- 一双会跟随光标的眼睛：把物联网"感知"拟人化，光标移到哪瞳孔看向哪 -->
      <div ref="watcherRef" class="watcher" aria-hidden="true">
        <span class="eye"><span class="pupil"></span></span>
        <span class="eye"><span class="pupil"></span></span>
      </div>

      <h1 class="title">{{ title }}</h1>
      <p class="sub">基于教材与培养方案的 RAG 学科知识问答</p>

      <div class="tagline" aria-hidden="true">
        <span>向量检索</span><i></i><span>混合召回</span><i></i><span>引用溯源</span><i></i><span>多智能体</span>
      </div>

      <el-card class="card">
        <span class="card-shine" aria-hidden="true"></span>
        <el-form :model="form" size="large" @keyup.enter="submit">
          <el-form-item>
            <el-input v-model="form.username" placeholder="用户名" autocomplete="username">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="form.password" type="password" placeholder="密码"
              show-password autocomplete="current-password"
              @focus="onPwdFocus" @blur="onPwdBlur"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-button class="submit" type="primary" size="large" :loading="loading" @click="submit">
            <span class="submit-text">登 录</span>
            <span class="submit-glow" aria-hidden="true"></span>
          </el-button>
        </el-form>

        <div class="demo">
          <span class="demo-label">演示账号</span>
          <button
            v-for="acc in demoAccounts" :key="acc.username" type="button" class="chip"
            @click="fill(acc)"
          >
            {{ acc.label }}
          </button>
        </div>
      </el-card>

      <p class="foot">南京邮电大学 · 物联网学院</p>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 登录页：深色科技风。
 *
 * 背景是可交互的粒子互联网络 —— 物联网的视觉隐喻，鼠标移入时近邻节点会被拉亮。
 * 动效全部服从 prefers-reduced-motion；页面不可见时停掉动画循环，别空转烧电。
 */
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = reactive({ username: 'admin', password: 'admin123' })
const loading = ref(false)
/** 标题内容。整条标题一起做入场与扫光 —— 逐字动画和渐变文字不能共存：
 *  逐字动画的 filter/transform 会给每个字建独立层叠上下文，
 *  而字是 color: transparent 靠父级 background-clip: text 上色的，
 *  一旦独立成层就什么都画不出来（实测整条标题会消失）。 */
const title = '物联网学科大模型教学实验平台'

const demoAccounts = [
  { label: '管理员', username: 'admin', password: 'admin123' },
  { label: '教师', username: 'teacher', password: 'teacher123' },
  { label: '学生', username: 'student', password: 'student123' },
]

function fill(acc: { username: string; password: string }) {
  form.username = acc.username
  form.password = acc.password
}

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    router.push((route.query.next as string) || '/')
  } finally {
    loading.value = false
  }
}

// ---------------- 鼠标视差 ----------------
const parallax = ref<Record<string, string>>({})
function onMouseMove(e: MouseEvent) {
  const cx = window.innerWidth / 2
  const cy = window.innerHeight / 2
  // 位移很小：只是"卡片有厚度"的暗示，幅度大了会晕
  parallax.value = {
    '--px': `${((e.clientX - cx) / cx) * 6}px`,
    '--py': `${((e.clientY - cy) / cy) * 6}px`,
  }
  pointer.x = e.clientX
  pointer.y = e.clientY
  pointer.active = true
  scheduleEyes()
}
function onMouseLeave() {
  parallax.value = { '--px': '0px', '--py': '0px' }
  pointer.active = false
  updateEyes()
}

// ---------------- 跟随光标的眼睛 ----------------
const watcherRef = ref<HTMLElement | null>(null)
const pwdFocused = ref(false)
let eyeRaf = 0
/** 瞳孔跟随鼠标：算每个眼中心到光标的夹角，把瞳孔沿该方向推到最大偏移。
 *  输入密码时改成"低头看键盘"，是一个常见的贴心小动作。 */
function updateEyes() {
  if (reducedMotion()) return
  const watcher = watcherRef.value
  if (!watcher) return
  const eyes = watcher.querySelectorAll<HTMLElement>('.eye')
  const MAX = 13
  eyes.forEach((eye) => {
    const r = eye.getBoundingClientRect()
    const cx = r.left + r.width / 2
    const cy = r.top + r.height / 2
    let dx = 0
    let dy = 0
    if (pwdFocused.value) {
      dy = MAX
    } else if (pointer.active) {
      const ang = Math.atan2(pointer.y - cy, pointer.x - cx)
      dx = Math.cos(ang) * MAX
      dy = Math.sin(ang) * MAX
    }
    eye.style.setProperty('--dx', dx.toFixed(1) + 'px')
    eye.style.setProperty('--dy', dy.toFixed(1) + 'px')
  })
}
function scheduleEyes() {
  if (eyeRaf) return
  eyeRaf = requestAnimationFrame(() => {
    eyeRaf = 0
    updateEyes()
  })
}
function onPwdFocus() {
  pwdFocused.value = true
  updateEyes()
}
function onPwdBlur() {
  pwdFocused.value = false
  updateEyes()
}

// ---------------- 粒子互联网络 ----------------
const canvasEl = ref<HTMLCanvasElement | null>(null)
const pointer = reactive({ x: 0, y: 0, active: false })
let rafId = 0
let ctx: CanvasRenderingContext2D | null = null
let nodes: { x: number; y: number; vx: number; vy: number; r: number }[] = []
let dpr = 1

const LINK_DIST = 132
const POINTER_DIST = 168

function reducedMotion() {
  return typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function resize() {
  const el = canvasEl.value
  if (!el) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = el.clientWidth
  const h = el.clientHeight
  el.width = Math.round(w * dpr)
  el.height = Math.round(h * dpr)
  ctx = el.getContext('2d')
  ctx?.scale(dpr, dpr)

  // 粒子数跟面积走：大屏密一些，小屏别挤成一团
  const count = Math.max(28, Math.min(88, Math.round((w * h) / 14000)))
  nodes = Array.from({ length: count }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.22,
    vy: (Math.random() - 0.5) * 0.22,
    r: Math.random() * 1.4 + 0.8,
  }))
}

function draw() {
  const el = canvasEl.value
  if (!el || !ctx) return
  const w = el.clientWidth
  const h = el.clientHeight
  ctx.clearRect(0, 0, w, h)

  for (const n of nodes) {
    n.x += n.vx
    n.y += n.vy
    if (n.x < 0 || n.x > w) n.vx *= -1
    if (n.y < 0 || n.y > h) n.vy *= -1
  }

  // 节点之间的连线：越近越亮
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]
      const b = nodes[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const d = Math.hypot(dx, dy)
      if (d < LINK_DIST) {
        const alpha = (1 - d / LINK_DIST) * 0.34
        ctx.strokeStyle = `rgba(90, 160, 255, ${alpha})`
        ctx.lineWidth = 0.8
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
    }
  }

  // 鼠标附近：节点拉亮并连到指针，做出"被感知"的互动
  for (const n of nodes) {
    let active = false
    if (pointer.active) {
      const d = Math.hypot(n.x - pointer.x, n.y - pointer.y)
      if (d < POINTER_DIST) {
        active = true
        const alpha = (1 - d / POINTER_DIST) * 0.5
        ctx.strokeStyle = `rgba(10, 132, 255, ${alpha})`
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(n.x, n.y)
        ctx.lineTo(pointer.x, pointer.y)
        ctx.stroke()
      }
    }
    ctx.fillStyle = active ? 'rgba(150, 205, 255, 0.95)' : 'rgba(120, 170, 240, 0.5)'
    ctx.beginPath()
    ctx.arc(n.x, n.y, active ? n.r * 1.6 : n.r, 0, Math.PI * 2)
    ctx.fill()
  }
}

function loop() {
  draw()
  rafId = requestAnimationFrame(loop)
}

function start() {
  cancelAnimationFrame(rafId)
  if (reducedMotion()) {
    draw() // 只画一帧静态画面
    return
  }
  loop()
}

function onVisibility() {
  if (document.hidden) cancelAnimationFrame(rafId)
  else start()
}

onMounted(() => {
  resize()
  start()
  window.addEventListener('resize', resize)
  document.addEventListener('visibilitychange', onVisibility)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  cancelAnimationFrame(eyeRaf)
  window.removeEventListener('resize', resize)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<style scoped lang="scss">
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  overflow: hidden;
  /* 登录页永远是深色：它是门面，跟随主题切换反而会削弱冲击力 */
  background:
    radial-gradient(1200px 600px at 15% 0%, #0d2340 0%, transparent 60%),
    radial-gradient(900px 500px at 85% 100%, #102a4d 0%, transparent 62%),
    #05070f;

  .bg-canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
  }

  /* 两团缓慢漂浮的光晕 */
  .glow {
    position: absolute;
    border-radius: 50%;
    filter: blur(70px);
    pointer-events: none;
    opacity: 0.55;
  }

  .glow-a {
    top: -140px;
    left: -80px;
    width: 460px;
    height: 460px;
    background: radial-gradient(circle, rgba(10, 132, 255, 0.55) 0%, rgba(10, 132, 255, 0) 70%);
    animation: float-a 18s ease-in-out infinite alternate;
  }

  .glow-b {
    right: -120px;
    bottom: -160px;
    width: 520px;
    height: 520px;
    background: radial-gradient(circle, rgba(48, 209, 200, 0.4) 0%, rgba(48, 209, 200, 0) 70%);
    animation: float-b 22s ease-in-out infinite alternate;
  }

  /* 网格：中间清晰、四周渐隐，做出纵深 */
  .grid {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(rgba(120, 180, 255, 0.07) 1px, transparent 1px),
      linear-gradient(90deg, rgba(120, 180, 255, 0.07) 1px, transparent 1px);
    background-size: 46px 46px;
    mask-image: radial-gradient(circle at 50% 45%, #000 0%, transparent 72%);
    -webkit-mask-image: radial-gradient(circle at 50% 45%, #000 0%, transparent 72%);
  }
}

@keyframes float-a {
  to {
    transform: translate3d(70px, 50px, 0) scale(1.12);
  }
}

@keyframes float-b {
  to {
    transform: translate3d(-60px, -40px, 0) scale(1.08);
  }
}

.stage {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate3d(var(--px, 0), var(--py, 0), 0);
  transition: transform 0.3s var(--ease);
}

/* ---------------- 徽标 ---------------- */
.badge {
  position: relative;
  width: 74px;
  height: 74px;
  margin-bottom: 18px;
  display: grid;
  place-items: center;
  animation: card-in 0.6s var(--ease) both;

  .core {
    position: relative;
    z-index: 1;
    display: grid;
    place-items: center;
    width: 58px;
    height: 58px;
    border-radius: 18px;
    color: #fff;
    background: linear-gradient(145deg, #0a84ff, #00c6fb);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 12px 26px rgba(10, 132, 255, 0.4);
  }

  /* 呼吸光环 */
  .ring {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 1px solid rgba(120, 190, 255, 0.55);
    animation: pulse 2.8s var(--ease) infinite;
  }
}

@keyframes pulse {
  0% {
    transform: scale(0.86);
    opacity: 0.9;
  }
  70% {
    transform: scale(1.18);
    opacity: 0;
  }
  100% {
    transform: scale(1.18);
    opacity: 0;
  }
}

/* ---------------- 跟随光标的眼睛 ---------------- */
.watcher {
  display: flex;
  gap: 18px;
  margin-bottom: 16px;
  animation: card-in 0.6s var(--ease) both;
}

.eye {
  position: relative;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  overflow: hidden;
  background: radial-gradient(circle at 50% 36%, #ffffff 0%, #dcebff 62%, #a9c8f5 100%);
  border: 1px solid rgba(140, 190, 255, 0.5);
  box-shadow:
    inset 0 -7px 13px rgba(20, 50, 90, 0.25),
    0 6px 18px rgba(10, 30, 60, 0.42);
  /* 这两个变量由 JS 写入，决定瞳孔偏移 */
  --dx: 0px;
  --dy: 0px;

  /* 玻璃高光，让眼白有立体感 */
  &::after {
    content: '';
    position: absolute;
    top: 7px;
    left: 9px;
    width: 13px;
    height: 9px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.85);
    filter: blur(1px);
    pointer-events: none;
  }
}

.pupil {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 18px;
  height: 18px;
  margin: -9px 0 0 -9px;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, #0a1a33 0%, #0a1a33 55%, #05070f 100%);
  /* 青色辉光呼应科技风强调色 */
  box-shadow:
    0 0 10px rgba(34, 211, 197, 0.7),
    inset 0 0 4px rgba(34, 211, 197, 0.5);
  transform: translate(var(--dx), var(--dy));
  transition: transform 0.12s ease-out;
}

/* ---------------- 标题 ---------------- */
.title {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.5px;
  /* 渐变色文字 + 缓慢扫光：background-position 在动，字形本身不建层叠上下文，
     所以能一直保持"被父级裁剪上色"的状态 */
  background: linear-gradient(100deg, #ffffff 0%, #9fd0ff 30%, #6cf0e0 52%, #ffffff 80%);
  background-size: 260% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 6px 24px rgba(64, 158, 255, 0.22));
  animation: fade-up 0.6s var(--ease) 0.05s both, title-sheen 7s ease-in-out infinite alternate;
}

@keyframes title-sheen {
  from {
    background-position: 0% 50%;
  }
  to {
    background-position: 100% 50%;
  }
}

.sub {
  margin: 0 0 14px;
  color: rgba(200, 220, 245, 0.72);
  font-size: 13px;
  animation: fade-up 0.6s var(--ease) 0.35s both;
}

.tagline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 22px;
  color: rgba(160, 190, 225, 0.62);
  font-size: 12px;
  animation: fade-up 0.6s var(--ease) 0.45s both;

  i {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: rgba(120, 180, 255, 0.6);
  }
}

/* ---------------- 玻璃卡片 ---------------- */
.card {
  position: relative;
  width: 392px;
  max-width: 92vw;
  padding: 10px 14px;
  border: 1px solid rgba(140, 190, 255, 0.22);
  border-radius: var(--radius-lg);
  background: rgba(16, 26, 44, 0.62);
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  --el-box-shadow-light: 0 24px 60px rgba(2, 8, 20, 0.55);
  overflow: hidden;
  animation: card-in 0.6s var(--ease) 0.1s both;

  /* 斜向流光扫过卡片表面，慢速、低透明度，只做质感 */
  .card-shine {
    position: absolute;
    top: -60%;
    left: -30%;
    width: 60%;
    height: 220%;
    background: linear-gradient(90deg, transparent, rgba(160, 210, 255, 0.14), transparent);
    transform: rotate(18deg);
    animation: shine 7.5s var(--ease) infinite;
    pointer-events: none;
  }

  :deep(.el-input__wrapper) {
    background: rgba(8, 16, 30, 0.62);
    box-shadow: inset 0 0 0 1px rgba(140, 190, 255, 0.18);
    transition: box-shadow 0.25s var(--ease), background 0.25s var(--ease);

    &.is-focus,
    &:hover {
      background: rgba(10, 20, 38, 0.78);
      box-shadow: inset 0 0 0 1px var(--brand), 0 0 0 4px rgba(10, 132, 255, 0.16);
    }
  }

  :deep(.el-input__inner) {
    color: #eaf3ff;

    &::placeholder {
      color: rgba(170, 195, 225, 0.55);
    }
  }

  :deep(.el-form-item) {
    animation: fade-up 0.5s var(--ease) both;
  }

  :deep(.el-form-item:nth-child(1)) {
    animation-delay: 0.18s;
  }

  :deep(.el-form-item:nth-child(2)) {
    animation-delay: 0.24s;
  }
}

@keyframes shine {
  0% {
    transform: translateX(-120%) rotate(18deg);
  }
  55%,
  100% {
    transform: translateX(360%) rotate(18deg);
  }
}

/* ---------------- 登录按钮 ---------------- */
.submit {
  position: relative;
  width: 100%;
  margin-top: 4px;
  border: none;
  overflow: hidden;
  font-weight: 600;
  letter-spacing: 2px;
  background: linear-gradient(96deg, #0a84ff 0%, #3fb0ff 48%, #14c8d8 100%);
  background-size: 180% 100%;
  box-shadow: 0 10px 26px rgba(10, 132, 255, 0.35);
  animation: fade-up 0.5s var(--ease) 0.3s both, hue 9s ease-in-out infinite alternate;

  .submit-text {
    position: relative;
    z-index: 1;
  }

  /* hover 时一道高光扫过 */
  .submit-glow {
    position: absolute;
    top: 0;
    left: -40%;
    width: 40%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.5), transparent);
    transform: skewX(-18deg);
    opacity: 0;
  }

  &:hover {
    box-shadow: 0 14px 32px rgba(10, 132, 255, 0.45);

    .submit-glow {
      opacity: 1;
      animation: sweep 0.9s var(--ease);
    }
  }

  &:active {
    transform: translateY(1px);
  }
}

@keyframes sweep {
  from {
    left: -40%;
  }
  to {
    left: 120%;
  }
}

@keyframes hue {
  to {
    background-position: 100% 50%;
  }
}

/* ---------------- 演示账号 ---------------- */
.demo {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  flex-wrap: wrap;
  animation: fade-up 0.5s var(--ease) 0.36s both;

  .demo-label {
    color: rgba(170, 195, 225, 0.6);
    font-size: 12px;
  }

  .chip {
    padding: 3px 11px;
    border: 1px solid rgba(140, 190, 255, 0.26);
    border-radius: var(--radius-pill);
    background: rgba(20, 34, 56, 0.6);
    color: #cfe4ff;
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
    transition: border-color 0.2s var(--ease), background 0.2s var(--ease),
      transform 0.2s var(--ease), box-shadow 0.2s var(--ease);

    &:hover {
      border-color: var(--brand);
      background: rgba(10, 132, 255, 0.2);
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba(10, 132, 255, 0.28);
    }
  }
}

.foot {
  margin: 20px 0 0;
  color: rgba(150, 180, 215, 0.42);
  font-size: 12px;
  letter-spacing: 1px;
  animation: fade-up 0.6s var(--ease) 0.5s both;
}

/* 小屏：卡片撑满、标题缩小，别让标题换行成三行 */
@media (max-width: 520px) {
  .title {
    font-size: 20px;
  }

  .tagline {
    display: none;
  }
}
</style>
