# 基本配置

与 `.env.example` 顶部 **Quick start** 对齐。不写架构全书，不列 Tushare 全量接口。产品对照见仓库 README「产品介绍」。

## 必填（推荐安装）

| 变量 | 含义 |
| --- | --- |
| `TA_ADMIN_PASSWORD` | 首次启动创建管理员。字母+数字、≥8 位。未设置则拒绝启动 |
| `TA_APP_SECRET_KEY` | JWT / 加密用户 Key，≥32 字节。生产必改 |
| `DATABASE_URL` | 建议 `sqlite:///./data/tradingagents.db`（先建 `data/`） |
| `TA_ALLOW_REGISTRATION` | 推荐 `0`（空库只有管理员） |
| `TA_ADMIN_USERNAME` / `TA_ADMIN_EMAIL` | 默认 `admin` / `admin@localhost` |

## 推荐（才能跑分析）

| 变量 | 含义 |
| --- | --- |
| `TA_API_KEY` / `TA_BASE_URL` / `TA_LLM_PROVIDER` | 默认 LLM；也可只在「设置」里配用户级 Key |
| `TUSHARE_TOKEN` | A 股数据。无 token 时部分行情为空，UI 仍可进 |

## 开关

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TA_TUSHARE_L2_ENABLED` | `0` | **opt-in**。Tushare L2 / 委托队列；无权限返回空，分析继续。不是开箱功能 |
| `TA_FAST_ANALYSIS_ENABLED` | `0` | 快速分析（约两分钟单轮 LLM） |
| `TA_USER_TASK_QUEUE_ENABLED` | `1` | 任务中心 |
| `TA_QLIB_EVAL_ENABLED` / `TA_QLIB_BRIDGE_ENABLED` 等 | `0` | 独立 `QLIB/` 工作区；不在 Docker 镜像内 |
| `TA_COST_ANALYSIS` | 环境默认 | 智能分析扣点 |

## 不要当作必做

Electron、`TA_DEV_API_PORT`、Vite 5173、本机 MySQL 密码、Windows Postgres 家目录等，只属于开发附录。见 [install.md](install.md)。

生产务必修改管理员口令与 `TA_APP_SECRET_KEY`。
