# Dev Launcher 编排器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `scripts/dev-launcher-electron` 重构为「单实例 + 双进程启动 + 状态机编排 + DevOps 控制台 UI」，并与仓库真实的 API 端口（默认 8001）、Vite 代理、SQLite/DATABASE_URL 对齐。

**Architecture:** Main 进程拆分模块：`env-resolver`、`port-claim`、`process-supervisor`、`orchestrator`、`health-gate`、`db-inspector`、`log-router`；智能一键走状态机；Renderer 通过 IPC 订阅阶段与分通道日志。

**Tech Stack:** Electron 34、Node 子进程、PowerShell（Windows 端口释放）、原生 `http`/`net` 探测。

---

## 文件映射（新建 / 修改）

| 路径 | 职责 |
|------|------|
| 新建 `scripts/dev-launcher-electron/lib/env-resolver.cjs` | 解析仓库根 `.env`，导出 `getApiPort()`, `getDatabaseUrlHint()`, `mergedEnvForChildren()` |
| 新建 `scripts/dev-launcher-electron/lib/port-claim.cjs` | Windows：释放 8000/8001/5173-5180 监听 |
| 新建 `scripts/dev-launcher-electron/lib/process-supervisor.cjs` | 管理 `apiChild`/`webChild`，spawn、kill、日志回调 |
| 新建 `scripts/dev-launcher-electron/lib/health-gate.cjs` | `/healthz` + 前端 URL 轮询 |
| 新建 `scripts/dev-launcher-electron/lib/db-inspector.cjs` | SQLite 路径、大小、WAL；可选 `sqlite3` 表数量 |
| 新建 `scripts/dev-launcher-electron/lib/orchestrator.cjs` | 状态机 + `orch:start` 入口 |
| 新建 `scripts/dev-launcher-electron/lib/log-router.cjs` | 统一 `emitLog(channel, line)` |
| 修改 `scripts/dev-launcher-electron/main.cjs` | 瘦入口：`requestSingleInstanceLock`、注册 IPC、`createWindow` |
| 修改 `scripts/dev-launcher-electron/preload.cjs` | 暴露 `orchStart`、`orchStop`、`onPhase`、`onLogChunk`、`getResolvedPorts` |
| 修改 `renderer/index.html` | DevOps 布局：流水线、三卡片、日志 Tab |
| 修改 `renderer/styles.css` | 控制台视觉 |
| 新建 `renderer/dashboard.js`（或重写 `app.js`） | 绑定 UI 与 IPC |

---

### Task 1: `env-resolver.cjs`（API 端口与 DATABASE_URL）

**Files:**
- Create: `scripts/dev-launcher-electron/lib/env-resolver.cjs`

- [ ] **Step 1: 新建模块**

实现要点：
- `ROOT` 由调用方传入 `path.resolve(__dirname,'../..')` 或由模块内 `path.join(__dirname,'..','..')` 固定为 launcher 上两级（与现 `main.cjs` 一致）。
- 使用 `fs.readFileSync` 读取 `.env`，按行解析 `KEY=VALUE`，忽略 `#`；**不得**将值写入控制台日志。
- `getApiPort()`：`Number(env.TA_DEV_API_PORT || env.PORT || 8001)`。
- `getDatabaseUrl()`：`process.env.DATABASE_URL || dotenv.DATABASE_URL || 'sqlite:///./tradingagents.db'`（与 `api/database.py` 默认一致，仅用于展示解析）。
- 导出 `loadEnv(ROOT)` 返回 `{ raw, apiPort, databaseUrl }`。

- [ ] **Step 2: 本地快速验证**

在仓库根执行：

```bash
node -e "const m=require('./scripts/dev-launcher-electron/lib/env-resolver.cjs'); console.log(m.loadEnv(process.cwd()))"
```

预期：输出对象含 `apiPort` 数字、无抛错（无 `.env` 时仍返回默认）。

- [ ] **Step 3: Commit**

```bash
git add scripts/dev-launcher-electron/lib/env-resolver.cjs
git commit -m "feat(launcher): add env resolver for API port and DATABASE_URL"
```

---

### Task 2: `port-claim.cjs` + 单实例锁

**Files:**
- Create: `scripts/dev-launcher-electron/lib/port-claim.cjs`
- Modify: `scripts/dev-launcher-electron/main.cjs`（文件头与 `app.whenReady` 前）

- [ ] **Step 1: 端口释放函数**

`claimDevPortsWin()` 内联单条 PowerShell（与规约 8000,8001,5173-5180）：

```js
// port-claim.cjs
const { execFile } = require('child_process');
function claimDevPortsWin() {
  const ps = '$ports=@(8000,8001)+(5173..5180); foreach($p in $ports){ Get-NetTCPConnection -LocalPort $p -State Listen -EA 0 | % { if([int]$_.OwningProcess -gt 4){ Stop-Process -Id $_.OwningProcess -Force -EA 0 } } }';
  return new Promise((resolve, reject) => {
    execFile('powershell.exe', ['-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-Command', ps], { windowsHide: true }, (err) => (err ? reject(err) : resolve()));
  });
}
module.exports = { claimDevPortsWin };
```

非 `win32` 时导出空操作 `async () => {}` 并写注释「Phase 2」。

- [ ] **Step 2: 在 `main.cjs` 最前（`app.whenReady` 之前）加入：**

```js
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
  process.exit(0);
}
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});
```

- [ ] **Step 3: Commit**

```bash
git add scripts/dev-launcher-electron/lib/port-claim.cjs scripts/dev-launcher-electron/main.cjs
git commit -m "feat(launcher): single instance lock and Windows port claim helper"
```

---

### Task 3: `process-supervisor.cjs`（双进程）

**Files:**
- Create: `scripts/dev-launcher-electron/lib/process-supervisor.cjs`

- [ ] **Step 1: 实现 API / Web 启动**

```js
const { spawn } = require('child_process');
const path = require('path');

function createSupervisor({ root, onLine }) {
  let apiChild = null;
  let webChild = null;

  function startApi(extraEnv) {
    if (apiChild) return;
    apiChild = spawn(process.execPath, [path.join(root, 'scripts', 'dev-api.mjs')], {
      cwd: root,
      shell: false,
      windowsHide: true,
      env: { ...process.env, ...extraEnv, PYTHONUTF8: '1' },
    });
    pipe(apiChild, 'api', onLine);
  }

  function startWeb() {
    if (webChild) return;
    const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
    webChild = spawn(npm, ['run', 'dev:web'], { cwd: root, shell: true, windowsHide: true, env: { ...process.env } });
    pipe(webChild, 'web', onLine);
  }

  function pipe(child, ch, cb) {
    child.stdout?.on('data', (d) => d.toString('utf8').split(/\r?\n/).filter(Boolean).forEach((l) => cb(ch, 'stdout', l)));
    child.stderr?.on('data', (d) => d.toString('utf8').split(/\r?\n/).filter(Boolean).forEach((l) => cb(ch, 'stderr', l)));
  }

  function killTree(child) {
    if (!child || child.killed) return;
    if (process.platform === 'win32') {
      try { require('child_process').spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); } catch (_) {}
    } else {
      try { child.kill('SIGTERM'); } catch (_) {}
    }
  }

  function stopAll() {
    killTree(webChild); webChild = null;
    killTree(apiChild); apiChild = null;
  }

  return { startApi, startWeb, stopAll, get apiPid() { return apiChild?.pid }, get webPid() { return webChild?.pid } };
}

module.exports = { createSupervisor };
```

- [ ] **Step 2: Commit**

```bash
git add scripts/dev-launcher-electron/lib/process-supervisor.cjs
git commit -m "feat(launcher): process supervisor for api and web dev servers"
```

---

### Task 4: `orchestrator.cjs` + IPC 接线

**Files:**
- Create: `scripts/dev-launcher-electron/lib/orchestrator.cjs`
- Modify: `scripts/dev-launcher-electron/main.cjs`

- [ ] **Step 1: 编排顺序**

伪代码顺序（与规约一致）：

1. `emitPhase('preflight')` —— 检查 `ROOT/package.json`、`frontend/package.json` 存在。
2. `emitPhase('claim_ports')` —— `claimDevPortsWin()`；`supervisor.stopAll()`。
3. `emitPhase('deps')` —— 若无 `node_modules` → `npm install`；若无 `frontend/node_modules` → `npm --prefix frontend install`；可选 `uv sync`（IPC 选项）。
4. `emitPhase('optional_build')` —— 若选项 → `npm --prefix frontend run build`。
5. `emitPhase('start_api')` —— `loadEnv(ROOT)`，`startApi({ TA_DEV_API_PORT: String(apiPort) })`。
6. `emitPhase('start_web')` —— `startWeb()`。
7. `emitPhase('wait_ready')` —— 调用 `health-gate`（Task 5）直到超时。
8. `emitPhase('ready')` 或 `failed`。

- [ ] **Step 2: IPC**

- `ipcMain.handle('orch:start', handler)` 返回 `{ ok, phase }`。
- 所有阶段通过 `win.webContents.send('orch:phase', { phase, detail })`。

- [ ] **Step 3: 删除或停用** 旧逻辑中单进程 `npm run dev` 与固定 **8000** 健康检查；`getStatus` 改用 `env-resolver` 的端口 + `health-gate`。

- [ ] **Step 4: Commit**

```bash
git add scripts/dev-launcher-electron/lib/orchestrator.cjs scripts/dev-launcher-electron/main.cjs
git commit -m "feat(launcher): orchestrator FSM and IPC phases"
```

---

### Task 5: `health-gate.cjs` + `getStatus` 对齐

**Files:**
- Create: `scripts/dev-launcher-electron/lib/health-gate.cjs`
- Modify: `scripts/dev-launcher-electron/main.cjs`（`status:get`）

- [ ] **Step 1: 实现**

- `waitReady({ apiPort, timeoutMs })`：循环 `http.get('http://127.0.0.1:'+apiPort+'/healthz')`。
- `findWebPort()`：对 `5173..5180` 依次 `http.get('http://127.0.0.1:'+p+'/')`，首个 2xx/3xx 即返回 `p`。
- `getStatusSnapshot()` 返回 `{ apiListen, webListen, apiOk, webOk, apiPort, webPort, apiPids, webPids }`，PID 获取可复用现有 PowerShell `Get-NetTCPConnection` 辅助函数（从 `main.cjs` 抽出到 `lib/net-win.cjs` 可选）。

- [ ] **Step 2: Commit**

```bash
git add scripts/dev-launcher-electron/lib/health-gate.cjs scripts/dev-launcher-electron/main.cjs
git commit -m "fix(launcher): health checks use resolved API port and Vite port scan"
```

---

### Task 6: `db-inspector.cjs` + IPC `db:info`

**Files:**
- Create: `scripts/dev-launcher-electron/lib/db-inspector.cjs`
- Modify: `scripts/dev-launcher-electron/main.cjs`、`preload.cjs`

- [ ] **Step 1: SQLite 解析**

- 若 `DATABASE_URL` 以 `sqlite` 开头：解析路径（`sqlite:///` 与相对 `./` 相对于 `ROOT`），`fs.statSync`，检测同目录 `.wal`/`.shm`；若 `sqlite3` 在 PATH，执行 `sqlite3 <path> ".tables"` 用换行数近似表数（或 `SELECT count(*) FROM sqlite_master WHERE type='table'` 通过 `sqlite3 -json`）。

- [ ] **Step 2: Commit**

```bash
git add scripts/dev-launcher-electron/lib/db-inspector.cjs scripts/dev-launcher-electron/main.cjs scripts/dev-launcher-electron/preload.cjs
git commit -m "feat(launcher): read-only sqlite db inspector panel"
```

---

### Task 7: Renderer DevOps UI

**Files:**
- Modify: `scripts/dev-launcher-electron/renderer/index.html`
- Modify: `scripts/dev-launcher-electron/renderer/styles.css`
- Create 或重写: `scripts/dev-launcher-electron/renderer/dashboard.js`（若保留 `app.js` 则整文件替换引用）

- [ ] **Step 1: 布局**

- 顶栏：状态 +「智能一键」「停止」。
- `#pipeline`：步骤 DOM，监听 `orch:phase` 切换 `.is-active` / `.is-error`。
- `#cards`：API / Web / DB 三卡片，定时 `getStatus` + 一次 `db:info`。
- `#logs`：`tab` 切换 channel；订阅 `log:chunk`。

- [ ] **Step 2: Commit**

```bash
git add scripts/dev-launcher-electron/renderer/
git commit -m "feat(launcher): devops dashboard UI for orchestrator"
```

---

### Task 8: 退出行为与验收自测

**Files:**
- Modify: `scripts/dev-launcher-electron/main.cjs`

- [ ] **Step 1: `before-quit`**

若用户勾选「退出停止」：`supervisor.stopAll()` + Windows `claimDevPortsWin()`（与规约一致）。

- [ ] **Step 2: 手动验收清单**

1. 双击 `一键启动.bat`，第二次启动应聚焦同一窗口。
2. 智能一键后浏览器打开 `http://127.0.0.1:<webPort>/`，API `healthz` 使用解析端口（默认 8001）。
3. 日志 Tab 中 API 与 Web 输出分离。
4. 数据库卡片显示 `tradingagents.db` 路径与大小（默认配置下）。

- [ ] **Step 3: Commit**

```bash
git add scripts/dev-launcher-electron/main.cjs
git commit -m "fix(launcher): coordinated shutdown with port claim"
```

---

## 规格对照自检

| 规格章节 | 对应 Task |
|----------|-----------|
| 单实例 | Task 2 |
| 强接管端口 | Task 2 + Task 4 |
| 双进程与日志分流 | Task 3 + Task 7 |
| API 端口与 health | Task 1 + Task 5 |
| 数据库面板 | Task 6 |
| 状态机 | Task 4 |
| DevOps UI | Task 7 |

---

## 执行方式说明

**Plan complete and saved to `docs/superpowers/plans/2026-05-04-dev-launcher-orchestrator.md`. Two execution options:**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理实现并在 Task 间复核  
2. **Inline Execution** — 本会话按 Task 顺序直接改代码并跑验收

请选择其一。
