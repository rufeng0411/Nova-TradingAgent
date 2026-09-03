/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { execSync } from 'node:child_process'

function runGit(cmd: string): string {
  try {
    return execSync(cmd, { cwd: __dirname, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch {
    return ''
  }
}

function getBuildMeta() {
  const commit =
    process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ||
    runGit('git rev-parse --short HEAD') ||
    'unknown'

  const date =
    (process.env.VERCEL_GIT_COMMIT_TIMESTAMP
      ? new Date(process.env.VERCEL_GIT_COMMIT_TIMESTAMP).toISOString().slice(0, 10)
      : '') ||
    runGit('git show -s --format=%cd --date=format:%Y-%m-%d HEAD') ||
    new Date().toISOString().slice(0, 10)

  return {
    commit,
    date,
    version: `${date}+${commit}`,
  }
}

const buildMeta = getBuildMeta()
const devApiPort = process.env.TA_DEV_API_PORT || '8001'
const devApiTarget = `http://127.0.0.1:${devApiPort}`

/** 与 `vite dev` 一致；`vite preview` 需显式配置。目标用 127.0.0.1 避免 Windows 上 localhost→::1 而后端只绑 127.0.0.1 时代理 ECONNREFUSED。 */
const devApiProxy: Record<string, { target: string; changeOrigin: boolean; rewrite?: (p: string) => string }> = {
  '/api': {
    target: devApiTarget,
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
  '/v1': {
    target: devApiTarget,
    changeOrigin: true,
  },
  '/healthz': {
    target: devApiTarget,
    changeOrigin: true,
  },
  '/openapi.json': {
    target: devApiTarget,
    changeOrigin: true,
  },
  '/docs': {
    target: devApiTarget,
    changeOrigin: true,
  },
}

export default defineConfig({
  define: {
    __APP_BUILD_COMMIT__: JSON.stringify(buildMeta.commit),
    __APP_BUILD_DATE__: JSON.stringify(buildMeta.date),
    __APP_BUILD_VERSION__: JSON.stringify(buildMeta.version),
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // 默认可从本机 IPv4(127.0.0.1) 与局域网 IP 访问；仅监听 ::1 时，用 127.0.0.1:5173 会 ERR_CONNECTION_REFUSED
    host: true,
    port: 5173,
    // 5173 被占用时自动递增；启动器会探测 5173–5180 上可访问的前端
    strictPort: false,
    proxy: devApiProxy,
  },
  preview: {
    host: true,
    port: 4173,
    strictPort: true,
    proxy: devApiProxy,
  },
  test: {
    environment: 'jsdom',
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
  },
})
