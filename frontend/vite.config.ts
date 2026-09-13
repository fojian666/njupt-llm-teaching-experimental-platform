import { defineConfig, type ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Socket } from 'node:net'

/**
 * 后端没启动 / 中途挂掉时，vite 的代理默认只回一个光秃秃的 500，浏览器里看不出原因。
 * 这里换成带说明的 JSON，前端的响应拦截器会把 detail 弹成可读提示。
 */
function onProxyError(err: Error, _req: IncomingMessage, res: ServerResponse | Socket) {
  if (!('writeHead' in res) || res.headersSent) return
  res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
  res.end(
    JSON.stringify({
      detail: `后端没有响应（127.0.0.1:8000）。请确认已运行 ./start.sh back。原始错误：${err.message}`,
    }),
  )
}

const proxyTarget: ProxyOptions = {
  target: 'http://127.0.0.1:8000',
  changeOrigin: true,
  configure: (proxy) => {
    proxy.on('error', onProxyError)
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1', // 明确绑 IPv4 —— 默认 localhost 在本机解析成 ::1（IPv6-only），代理连不上
    port: 5173,
    // 全部 API 走代理转发到 Django：同源请求，省掉 cookie 跨域与 CSRF 的一堆坑
    proxy: {
      '/api': proxyTarget,
      '/media': proxyTarget,
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
