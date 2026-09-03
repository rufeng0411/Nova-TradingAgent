# Configure

Aligned with the **Quick start** block at the top of `.env.example`. No architecture book. No full Tushare API catalog. Product overview: repository README.

## Required (recommended install)

| Variable | Meaning |
| --- | --- |
| `TA_ADMIN_PASSWORD` | Creates the admin. Letters+digits, min 8. Missing → process refuses to start |
| `TA_APP_SECRET_KEY` | JWT / encrypt user keys, ≥32 bytes |
| `DATABASE_URL` | Prefer `sqlite:///./data/tradingagents.db` (create `data/` first) |
| `TA_ALLOW_REGISTRATION` | Prefer `0` (empty DB is admin-only) |
| `TA_ADMIN_USERNAME` / `TA_ADMIN_EMAIL` | Defaults `admin` / `admin@localhost` |

## Recommended (to run analysis)

| Variable | Meaning |
| --- | --- |
| `TA_API_KEY` / `TA_BASE_URL` / `TA_LLM_PROVIDER` | Default LLM; users can also save keys in Settings |
| `TUSHARE_TOKEN` | A-share data. UI still loads without it |

## Flags

| Variable | Default | Notes |
| --- | --- | --- |
| `TA_TUSHARE_L2_ENABLED` | `0` | **Opt-in.** Tushare L2 / order-queue; empty without entitlement; analysis continues. Not on by default |
| `TA_FAST_ANALYSIS_ENABLED` | `0` | Fast analysis (~two-minute single LLM pass) |
| `TA_USER_TASK_QUEUE_ENABLED` | `1` | Task center |
| `TA_QLIB_EVAL_ENABLED` / `TA_QLIB_BRIDGE_ENABLED` etc. | `0` | Isolated `QLIB/` workspace; not in the Docker image |
| `TA_COST_ANALYSIS` | env default | Credits per smart analysis |

Electron, Vite 5173, MySQL, and Windows Postgres homes are **not** required. See [install.md](install.md).
