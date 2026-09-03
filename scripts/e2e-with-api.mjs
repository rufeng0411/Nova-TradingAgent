/**
 * 全栈 Playwright：为子进程设置 E2E_START_API=1，由 playwright.config.ts 拉起 FastAPI。
 * API 端口由 TA_DEV_API_PORT 控制（默认 8001，与 dev-api.mjs 一致）。
 * 用法：在仓库根执行 `node scripts/e2e-with-api.mjs`（需已 `uv sync`）。
 * 或直接：TA_DEV_API_PORT=8001 node scripts/e2e-with-api.mjs --grep @live
 */
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const extra = process.argv.slice(2)

const r = spawnSync('npm', ['run', 'test:e2e', '--', ...extra], {
    cwd: path.join(root, 'frontend'),
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, E2E_START_API: '1' },
})

process.exit(r.status ?? 1)
