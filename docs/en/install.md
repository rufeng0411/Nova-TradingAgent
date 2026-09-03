# Install

Follow this page. Don’t mix the local-dev ports (Vite **5173** / API **8001**) with this path (built `frontend/dist` + uvicorn **8000**). Without `frontend/dist`, the UI won’t show.

What you get is a login-ready A-share research desk (fifteen-agent debate, K-line, optional L2/Qlib, credits and admin)—not an auto-trader. Product overview: [README.md](../../README.md).

## What you get

- Web desk at `http://127.0.0.1:8000`
- Empty SQLite database + default admin from `.env`
- Health JSON at `GET /healthz`

LLM keys (and optional Tushare) are required to **run** an analysis, not to open the UI.

## Prerequisites

- Python **3.10+**
- Node.js **18+** (the Docker image builds the frontend with Node 25; 18+ is enough locally)
- [uv](https://docs.astral.sh/uv/)
- Git

## Recommended steps

### 1. Clone

```bash
git clone https://github.com/rufeng0411/Nova-TradingAgent.git
cd Nova-TradingAgent
```

Private clone: `gh repo clone rufeng0411/Nova-TradingAgent`.

### 2. Environment

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

Edit `.env` and keep the top **Quick start** block:

| Variable | Rule |
| --- | --- |
| `TA_ADMIN_PASSWORD` | Letters + digits, min 8. Example `ChangeMe_Admin1!` passes strength checks |
| `TA_APP_SECRET_KEY` | ≥32 bytes. Change the example for anything reachable on a network |
| `DATABASE_URL` | `sqlite:///./data/tradingagents.db` |
| `TA_ALLOW_REGISTRATION` | Prefer `0` so the empty system has only the admin |
| `TA_ADMIN_USERNAME` / `TA_ADMIN_EMAIL` | Defaults `admin` / `admin@localhost` |

The process refuses to start if `TA_ADMIN_PASSWORD` is missing.

Optional: `TA_API_KEY`, `TUSHARE_TOKEN`. Leave `TA_TUSHARE_L2_ENABLED=0` unless you have a Tushare L2 entitlement. Missing L2 permission returns empty data; analysis continues.

### 3. Python deps

```bash
uv sync
```

### 4. Frontend build (required)

```bash
cd frontend
npm install
npm run build
cd ..
```

You must have `frontend/dist/`. If the build fails: Node ≥18, delete `frontend/node_modules`, retry `npm install`.

### 5. API (serves the SPA)

From the **repository root**:

```bash
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

### 6. Verify

1. Open `http://127.0.0.1:8000` — login page, not a blank screen.
2. `GET http://127.0.0.1:8000/healthz` — JSON, HTTP 200. There is no `/health`.
3. Sign in as `admin` (or `TA_ADMIN_USERNAME`) with `TA_ADMIN_PASSWORD`.
4. You should see an empty desk (no other users’ reports). With `TA_ALLOW_REGISTRATION=0` the login page has **no** sign-up link.

## Docker (optional, not the first-screen path)

Image: `ghcr.io/rufeng0411/Nova-TradingAgent`. Images publish when a `v*` tag is pushed. **Until that workflow has run, `docker pull` 404s** — use source install.

The image does **not** include Qlib.

Pass `TA_ADMIN_PASSWORD` and `TA_APP_SECRET_KEY`. Mount a data directory and set `DATABASE_URL=sqlite:///./data/tradingagents.db`.

## Developer appendix (don’t mix with the steps above)

- `npm run dev`: Vite **5173** + `scripts/dev-api.mjs` default API **8001**
- `docker-compose.dev.yml`, Electron launcher, local MySQL / Windows Postgres are optional

If the login page cannot fetch the API, you are probably on 5173 without the dev API, or uvicorn on 8000 is down.

## If you see X, do Y

| Symptom | Action |
| --- | --- |
| Blank page / API JSON only | No `frontend/dist`. Repeat step 4 |
| `TA_ADMIN_PASSWORD must be set` | `.env` missing or empty password; start from repo root |
| Password rejected | Min 8 chars, at least one letter and one digit |
| Failed to fetch | Use port 8000 for this path. The production SPA on :8000 talks to the same origin, not :8001 |
| `/health` 404 | Use `/healthz` |
| `uv` not found | Install uv and reopen the terminal |
| `npm run build` fails | Node ≥18; reinstall frontend deps |
| Port 8000 in use | Free the port or change it and the browser URL together |

Next: [user guide](user-guide.md).
