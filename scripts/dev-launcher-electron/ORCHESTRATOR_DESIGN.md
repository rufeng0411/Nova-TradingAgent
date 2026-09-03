# Dev Launcher 编排器（方案 C）设计说明

**日期：** 2026-05-04  
**状态：** 已定稿（基于用户确认的策略）

---

## 1. 背景与问题

当前 `scripts/dev-launcher-electron` 采用「单文件主进程 + 合并日志」方式启动根目录 `npm run dev`，存在：

1. **端口与健康检查与仓库真实约定不一致**：`scripts/dev-api.mjs` 默认 API 端口为 `TA_DEV_API_PORT` / `PORT`，否则 **8001**；`frontend/vite.config.ts` 代理目标亦为 `TA_DEV_API_PORT || '8001'`。启动器若固定探测 **8000**，会出现「显示未就绪 / 实际可用」的假阴性。
2. **进程模型不清晰**：仅持有单个 `npmChild`，无法区分 API / 前端日志，也难以对单侧重启。
3. **唯一性不足**：未强制单实例，用户可多开启动器导致重复释放端口或重复启动。
4. **「智能一键」缺少阶段模型**：用户期望一条流水线（预检 → 占端口 → 依赖 → 可选构建 → 启动 → 健康等待 → 就绪），失败需可定位步骤。
5. **数据库呈现缺失**：后端使用 `DATABASE_URL`（默认 SQLite `./tradingagents.db`），启动器未读取 `.env`、未展示路径与体积等开发时常用信息。

---

## 2. 目标与非目标

### 2.1 目标

- **单实例**：同一仓库同一时间只允许一个 Electron 启动器窗口（第二次启动应激活已有窗口或退出并提示）。
- **智能一键默认强接管**：用户已选择「占用目标端口则结束监听进程」，无需手工判断。
- **双进程开发模型**：与根 `package.json` 一致，分别启动  
  - `npm run dev:api` → `node scripts/dev-api.mjs`  
  - `npm run dev:web` → `npm --prefix frontend run dev`  
  以便 **API / Web 日志分流**，必要时可单独停止一侧。
- **统一端口与环境变量**：API 端口以 **`TA_DEV_API_PORT`（或 `PORT`）优先**，否则与 `dev-api.mjs` 默认一致（当前 **8001**）；前端端口扫描 **5173–5180**（与 Vite `strictPort: false` 一致）。
- **健康检查**：API `GET /healthz`（须使用解析后的 base URL）；前端对解析到的 dev URL 做 GET（接受 2xx/3xx）。
- **数据库面板（开发优先）**：解析 `DATABASE_URL`；若为 SQLite，展示 **解析后的绝对路径、文件大小、是否存在 WAL/SHM**；可选展示 **表数量**（若本机有 `sqlite3` CLI 则执行只读查询，否则降级为「仅路径与大小」）。
- **UI**：DevOps 控制台布局——**启动流水线 + 服务卡片 + 分通道日志 + 数据库卡片**，避免「按钮列表 + 单一日志」的落后体验。

### 2.2 非目标（本期不做）

- 生产环境部署编排（Docker/K8s）、远程主机监控。
- 在启动器内嵌入完整数据库管理（改表、跑迁移）；仅只读诊断信息。
- 跨平台退出时杀端口：Windows 已用 PowerShell；macOS/Linux 需后续单独任务（`lsof`/`fuser`），本期可在实现计划中列为 Phase 2。

---

## 3. 用户已确认的策略

| 项 | 选择 |
|----|------|
| 端口占用 | **完全自动**：目标端口被占用则结束监听进程 |
| UI 风格 | **DevOps 控制台**：流水线 + 卡片 + 分日志 |
| 数据库范围 | **开发优先**：`DATABASE_URL` + SQLite 路径/大小/WAL/表数量（可选） |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     Renderer（DevOps UI）                      │
│  流水线 │ API/Web/DB 卡片 │ 日志(api/web/orchestrator) │ 设置   │
└───────────────────────────┬─────────────────────────────────┘
                            │ IPC（invoke + push events）
┌───────────────────────────▼─────────────────────────────────┐
│ Main Process                                                  │
│  SingleInstanceLock │ Orchestrator FSM │ ProcessSupervisor   │
│  PortClaim(windows) │ EnvResolver │ HealthGate │ DbInspector   │
│  LogRouter → webContents.send('log:*')                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ spawn / exec / fs
              node dev-api.mjs    npm frontend dev    powershell
```

### 4.1 模块职责

| 模块 | 职责 |
|------|------|
| `single-instance` | `app.requestSingleInstanceLock()`；第二实例 `quit` 并 `focus` 主窗 |
| `env-resolver` | 读取仓库根 `.env`（不提交密钥到日志），解析 `DATABASE_URL`、`TA_DEV_API_PORT`、`PORT` |
| `port-claim` | Windows：PowerShell 结束监听于 **8000、8001、5173–5180**（与当前脚本范围对齐，且覆盖错误固定 8000 的历史探测） |
| `process-supervisor` | 维护 `apiChild`、`webChild`；启动、停止、退出码；杀进程树（Windows `taskkill /T /F`） |
| `health-gate` | 轮询 API `/healthz`、前端 URL；超时与退避策略可配置 |
| `db-inspector` | 解析 `DATABASE_URL`，SQLite 文件 stat；可选 `sqlite3 .tables` 计数 |
| `orchestrator` | 状态机驱动「智能一键」各阶段；向 Renderer 推送 `run:phase` |
| `log-router` | 将子进程 stdout/stderr 打上 channel，推送渲染层 |

---

## 5. 编排状态机（Orchestrator FSM）

建议状态（枚举字符串，IPC 传输）：

| 状态 ID | 含义 |
|---------|------|
| `idle` | 未运行一键流程 |
| `preflight` | 检测 node/npm/uv、根目录 `package.json`、可选 `.env` 可读 |
| `claim_ports` | 释放目标端口（强接管） |
| `deps` | 根目录 `npm install`（若缺 `node_modules`）；`npm --prefix frontend install`（若缺 `frontend/node_modules`）；可选 `uv sync`（勾选项保留） |
| `optional_build` | 可选 `frontend` 生产构建（勾选项） |
| `start_api` | 启动 `node scripts/dev-api.mjs`，注入解析后的 `TA_DEV_API_PORT` |
| `start_web` | 启动 `npm run dev:web` |
| `wait_ready` | 等待 API `/healthz` 与前端 HTTP 就绪 |
| `ready` | 全部就绪，允许「打开前端」 |
| `failed` | 某步失败，携带 `step`、`message`、`hint` |

**转移规则简述：**

- `preflight` 失败 → `failed`（例如缺少 `uv` 且 API 无法启动——由预检提示安装）。
- `claim_ports` 失败 → `failed`（PowerShell 异常）或重试一次后 `failed`。
- `deps` 中非零退出 → `failed`（构建类步骤除外可按产品决定：本期 **严格失败即停**）。
- `start_*` 子进程 `error` 事件 → `failed`。
- `wait_ready` 超时（例如 120s 可配置）→ `failed`，日志中写明探测 URL。

---

## 6. 端口与环境变量约定

| 变量 | 用途 |
|------|------|
| `TA_DEV_API_PORT` | 与 `dev-api.mjs`、`vite.config.ts` 一致，优先于 `PORT` |
| `PORT` | 次选 API 端口 |
| 默认 API 端口 | **8001**（与当前仓库脚本一致） |
| 前端扫描 | **5173–5180** 找首个 HTTP 响应的 dev server |

**启动器内部解析顺序：**

1. 读 `.env`（若存在）→ 内存合并（不向渲染进程打印秘密值）。
2. `apiPort = Number(process.env.TA_DEV_API_PORT || process.env.PORT || 8001)`。
3. 启动 API 子进程时 **显式设置** `env: { ...process.env, TA_DEV_API_PORT: String(apiPort) }`，避免用户全局环境陈旧。

健康检查 URL：`http://127.0.0.1:${apiPort}/healthz`。

---

## 7. IPC 契约（草案）

### 7.1 Renderer → Main

| Channel | 载荷 | 说明 |
|---------|------|------|
| `orch:start` | `{ uvSync?, build?, exitStopPorts? }` | 智能一键 |
| `orch:stop` | — | 停止由启动器拉起的 api/web，可选是否杀端口（设置项） |
| `orch:stop-api` / `orch:stop-web` | — | 单侧停止（高级） |
| `prefs:set` | `{ exitStopPorts: boolean }` | 退出行为 |

### 7.2 Main → Renderer（`webContents.send`）

| Event | 载荷 |
|-------|------|
| `orch:phase` | `{ phase, detail? }` |
| `log:chunk` | `{ channel: 'api'|'web'|'orch', level: 'stdout'|'stderr', line: string }` |
| `health:tick` | `{ apiOk, webOk, apiPort, webPort }` |
| `db:info` | `{ kind:'sqlite'|'other', path?, size?, wal?, tableCount? }` |

---

## 8. UI 信息架构（DevOps 控制台）

1. **顶栏**：总状态（idle / running / ready / failed）+ 主按钮「智能一键」+ 次按钮「停止」。
2. **流水线条**：横向步骤指示器，当前步骤高亮，失败步骤标红并展示原因一行。
3. **三卡片行**：API（端口、PID、健康）、Web（端口、PID、健康）、数据库（路径、大小、WAL、表数）。
4. **日志区**：Tab —— **全部 / API / Web / 编排**；支持清空、自动滚动；错误行高亮。
5. **设置抽屉或页**：`uv sync`、前端 build、退出杀端口（沿用现有偏好思路）。

视觉：深色背景、大圆角卡片、等宽日志、步骤条使用品牌色与明确的成功/失败色，避免「WinForms 列表感」。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 强杀端口误伤其它应用 | 端口集合与仓库约定绑定；日志明确写出被杀 PID；未来可加「仅杀 node/python 进程」二次过滤（可选） |
| `.env` 含密钥 | 预检与日志绝不打印完整密钥；仅展示「是否设置」类布尔 |
| macOS/Linux 杀端口未实现 | Phase 2；本期文档标注 Windows 一等公民 |

---

## 10. 验收标准

1. 仅允许一个启动器实例；第二次启动聚焦已有窗口。
2. 智能一键后 API 与前端日志分离可读；状态机步骤在 UI 可见。
3. 健康检查使用 **解析后的 API 端口**（默认 8001），与 `vite` 代理一致；前端端口识别 **5173–5180**。
4. 数据库卡片对默认 SQLite 至少展示路径与大小；在装有 `sqlite3` 时可显示表数量。
5. 失败时在流水线与日志中可定位到具体步骤。

---

## 11. 相关仓库文件（实现时需对照）

- `package.json`：`dev` / `dev:api` / `dev:web`
- `scripts/dev-api.mjs`：API 端口与 `uv run python`
- `frontend/vite.config.ts`：`TA_DEV_API_PORT`、`5173`、proxy
- `api/database.py`：`DATABASE_URL` 默认 SQLite

---

**实现阶段：** 见 `docs/superpowers/plans/2026-05-04-dev-launcher-orchestrator.md`。
