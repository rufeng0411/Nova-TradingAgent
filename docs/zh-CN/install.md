# 安装

陌生人请**只按本文**操作。不要混用开发端口（Vite 5173 / API 8001）和本路径的生产式端口（构建后的 `frontend/dist` + uvicorn **8000**）。无 `frontend/dist` 时 FastAPI **不会**挂上前端界面。

## 你将得到什么

- 本机 `http://127.0.0.1:8000` 的 Web 投研台
- SQLite 空库 + 默认管理员（`.env` 里的口令）
- 健康检查 `GET /healthz` 返回 JSON

分析功能还需要 LLM Key（和可选的 Tushare token）。不填也能登录进 UI。

## 前置

- Python **3.10+**
- Node.js **18+**（Docker 镜像构建前端用 Node 25；本机 18+ 即可）
- [uv](https://docs.astral.sh/uv/)（`uv sync`）
- Git

Windows PowerShell 与 macOS/Linux bash 命令如下。若某步报错，见文末「若出现 X 则做 Y」，或 [troubleshooting.md](troubleshooting.md)。

## 黄金路径（必须逐字执行）

### 1. 取得源码

```bash
git clone https://github.com/rufeng0411/Nova-TradingAgent.git
cd Nova-TradingAgent
```

私有阶段请用已登录的 GitHub CLI：`gh repo clone rufeng0411/Nova-TradingAgent`。

### 2. 环境文件

**PowerShell**

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force -Path data | Out-Null
```

**bash**

```bash
cp .env.example .env
mkdir -p data
```

打开 `.env`，确认顶部 **Quick start** 块已取消注释且已填写（示例口令仅供本地开发，生产必须改）：

| 变量 | 要求 |
| --- | --- |
| `TA_ADMIN_PASSWORD` | 字母+数字、至少 8 位。文档示例 `ChangeMe_Admin1!` 可通过强度校验 |
| `TA_APP_SECRET_KEY` | ≥32 字节。示例字符串已满足长度；生产请换成随机值 |
| `DATABASE_URL` | `sqlite:///./data/tradingagents.db` |
| `TA_ALLOW_REGISTRATION` | 建议 `0`，空系统只有管理员 |
| `TA_ADMIN_USERNAME` / `TA_ADMIN_EMAIL` | 默认 `admin` / `admin@localhost` |

未设置 `TA_ADMIN_PASSWORD` 时进程会拒绝启动。

可选：`TA_API_KEY`、`TUSHARE_TOKEN`。`TA_TUSHARE_L2_ENABLED` 保持 `0`，除非你确有 Tushare L2 权限。

### 3. Python 依赖

```bash
uv sync
```

### 4. 构建前端（必须）

```bash
cd frontend
npm install
npm run build
cd ..
```

成功后应存在 `frontend/dist/`。若构建失败，检查 Node 版本 ≥18，删除 `frontend/node_modules` 后重试 `npm install`。

### 5. 启动 API（同时托管 SPA）

在**仓库根目录**：

```bash
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

### 6. 验收

1. 浏览器打开 `http://127.0.0.1:8000`，应看到登录页（不是空白页）。
2. `GET http://127.0.0.1:8000/healthz` 应返回 JSON（HTTP 200）。不要请求 `/health`。
3. 用户名 `admin`（或 `.env` 中的 `TA_ADMIN_USERNAME`），密码为 `TA_ADMIN_PASSWORD`。
4. 登录后进入工作台。此时库中不应有他人用户或历史研报（空库）。

## Docker（可选，非第一屏）

镜像名：`ghcr.io/rufeng0411/Nova-TradingAgent`。镜像在推送 `v*` 标签后由 GitHub Actions 构建。**在构建完成前 `docker pull` 会 404**，请用上面的源码路径。

当前镜像**不含 Qlib**（Dockerfile 只拷 `api/`、`tradingagents/`、`scheduler/` 与前端 dist）。

容器内仍需传入 `TA_ADMIN_PASSWORD` 与 `TA_APP_SECRET_KEY`。数据目录建议挂载到 `/app/data`，并设置 `DATABASE_URL=sqlite:///./data/tradingagents.db`。

## 开发者附录（不要与黄金路径混用）

仅当你在改前端热重载时使用：

- `npm run dev`：Vite **5173** + `scripts/dev-api.mjs` 默认 API **8001**
- `docker-compose.dev.yml`、Electron 启动器、本机 MySQL / `D:\pgsql` 均为可选开发栈

生产式验收请回到步骤 4–6。登录页若提示连不上后端：确认你打开的是 `http://127.0.0.1:8000` 且 uvicorn 仍在运行。

## 若出现 X 则做 Y

| 现象 | 处理 |
| --- | --- |
| 页面空白 / 只有 API JSON | 未构建 `frontend/dist`。执行步骤 4 |
| `TA_ADMIN_PASSWORD must be set` | `.env` 未加载或口令为空。确认在仓库根启动，且 `.env` 有 Quick start 块 |
| 密码强度错误 | 至少 8 位且同时含字母和数字 |
| 登录 Failed to fetch | 开错了 5173，或 API 没起。黄金路径只用 8000。若页面在 8000 仍报连不上，请确认用的是本仓库已修复的前端构建（同源 `/v1`），不要指向 8001 |
| `/health` 404 | 正确路径是 `/healthz` |
| `uv` 找不到 | 安装 uv 后重开终端 |
| `npm run build` 失败 | Node ≥18；清 `frontend/node_modules` 重装 |
| 端口 8000 占用 | 换端口并同步访问 URL，或结束占用进程 |

下一步：[使用手册](user-guide.md)。
