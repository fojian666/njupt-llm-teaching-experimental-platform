<template>
  <!-- 复用 el-statistic 自身的类名，保证与有数据的卡片排版完全一致 -->
  <el-statistic v-if="value != null" :title="title" :value="display" :precision="precision" :suffix="suffix" />
  <div v-else class="el-statistic">
    <div class="el-statistic__head">{{ title }}</div>
    <div class="el-statistic__content">—</div>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    value: number | null | undefined
    precision?: number
    suffix?: string
    duration?: number
  }>(),
  { precision: 0, suffix: '', duration: 800 },
)

const display = ref(0)
let raf = 0

function animate(to: number) {
  cancelAnimationFrame(raf)
  const from = display.value
  const start = performance.now()

  const step = (now: number) => {
    const p = Math.min(1, (now - start) / props.duration)
    const eased = 1 - Math.pow(1 - p, 3) // easeOutCubic：起步快、收尾稳
    display.value = from + (to - from) * eased
    if (p < 1) raf = requestAnimationFrame(step)
    else display.value = to
  }
  raf = requestAnimationFrame(step)
}

watch(
  () => props.value,
  (v) => {
    if (v == null) {
      display.value = 0
      return
    }
    animate(Number(v))
  },
  { immediate: true },
)

onUnmounted(() => cancelAnimationFrame(raf))
</script>
