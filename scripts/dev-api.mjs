/**
 * 开发环境启动 FastAPI（与根目录 npm run dev 配套）。
 * - 优先使用 uv（与项目 pyproject 依赖一致）；从资源管理器/Electron 启动时 PATH 可能不含 uv，会补常见安装路径。
 * - 若无 uv，回退到 python -m uvicorn（可能缺依赖，仅作兜底提示）。
 */
import { spawn, execSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
process.chdir(root)

function augmentPathWin() {
  if (process.platform !== 'win32') return
  const extra = [
    path.join(process.env.USERPROFILE || '', '.local', 'bin'),
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'uv'),
    path.join(process.env.LOCALAPPDATA || '', 'uv'),
  ].filter(Boolean)
  const sep = path.delimiter
  process.env.PATH = [...extra, process.env.PATH || ''].join(sep)
}

function hasUv() {
  try {
    execSync('uv --version', { stdio: 'ignore', shell: true })
    return true
  } catch {
    return false
  }
}

const apiPort = process.env.TA_DEV_API_PORT || process.env.PORT || '8001'
// 限制热重载监视目录，避免 Vite 写 frontend/node_modules 等触发整站 reload，
// 在 lifespan 尚未完成时出现 8001 短暂无监听，进而导致 Vite 代理 ECONNREFUSED。
// reload-delay：变更需稳定超过该秒数才重载，减轻 Windows 上 mtime 抖动 / 索引软件
// 在「Waiting for application startup」阶段误触 cn_*.py 等导致的过早 Reload。
// reload-exclude database.py：该文件常被格式化/IDE 触碰，一改就整进程重载，易与长启动的
// LangGraph / DB 初始化叠在一起，导致 Vite 侧 ECONNRESET/ECONNREFUSED；改 engine 层后请手动重启 API。
const reloadDelaySec = (process.env.TA_DEV_UVICORN_RELOAD_DELAY ?? '2').trim() || '2'
const uvicornArgs = [
  '-m',
  'uvicorn',
  'api.main:app',
  '--host',
  '0.0.0.0',
  '--port',
  apiPort,
  '--reload',
  '--reload-delay',
  reloadDelaySec,
  '--reload-exclude',
  'api/database.py',
  '--reload-dir',
  'api',
  '--reload-dir',
  'tradingagents',
]
const childOpts = { stdio: 'inherit', shell: true, cwd: root, env: { ...process.env } }

augmentPathWin()

function onExit(code) {
  process.exit(code ?? 0)
}

if (hasUv()) {
  const child = spawn('uv', ['run', 'python', ...uvicornArgs], childOpts)
  child.on('exit', onExit)
  child.on('error', (err) => {
    console.error('[dev-api]', err.message)
    process.exit(1)
  })
} else {
  console.error('[dev-api] 未在 PATH 中找到 uv。请安装 https://github.com/astral-sh/uv 并在项目根执行 uv sync')
  console.error('[dev-api] 回退：python -m uvicorn（若缺少 langchain_core 等依赖会启动失败）')
  const child = spawn('python', uvicornArgs, childOpts)
  child.on('exit', onExit)
  child.on('error', (err) => {
    console.error('[dev-api]', err.message)
    process.exit(1)
  })
}
