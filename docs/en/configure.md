# Configure

Aligned with the **Quick start** block at the top of `.env.example`. No architecture book. No full Tushare API catalog.

## Required (golden path)

| Variable | Meaning |
| --- | --- |
| `TA_ADMIN_PASSWORD` | Creates the admin. Letters+digits, min 8. Missing → process refuses to start |
| `TA_APP_SECRET_KEY` | JWT / encrypt user keys, ≥32 bytes |
| `DATABASE_URL` | Prefer `sqlite:///./data/tradingagents.db` (create `data/` first) |
| `TA_ALLOW_REGISTRATION` | Use `0` on the golden path |
| `TA_ADMIN_USERNAME` / `TA_ADMIN_EMAIL` | Defaults `admin` / `admin@localhost` |

## Recommended (to run analysis)

| Variable | Meaning |
| --- | --- |
| `TA_API_KEY` / `TA_BASE_URL` / `TA_LLM_PROVIDER` | Default LLM; users can also save keys in Settings |
| `TUSHARE_TOKEN` | A-share data. UI still loads without it |

## Flags

| Variable | Default | Notes |
| --- | --- | --- |
| `TA_TUSHARE_L2_ENABLED` | `0` | **Opt-in.** Needs a Tushare L2 entitlement; empty data otherwise; analysis continues |
| `TA_FAST_ANALYSIS_ENABLED` | `0` | Fast analysis |
| `TA_USER_TASK_QUEUE_ENABLED` | `1` | Task center |
| `TA_QLIB_*` | `0` | Qlib is not in the Docker image |
| `TA_COST_ANALYSIS` | env default | Credits per smart analysis |

Electron, Vite 5173, MySQL, and Windows Postgres homes are **not** required. See [install.md](install.md).
