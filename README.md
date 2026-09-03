# Nova-TradingAgent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md)

**Fifteen specialists. One A-share research desk.**

Run it on your own machine. Fifteen agents debate A-share names; the K-line desk can explain the chart; Tushare L2 order-queue is opt-in. Models see distilled conclusions, not raw dumps.

This is a **research workbench**. It does **not** place trades by default.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/rufeng0411/Nova-TradingAgent)](https://github.com/rufeng0411/Nova-TradingAgent/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**[Install](docs/en/install.md)** · **[User guide](docs/en/user-guide.md)** · **[Releases](https://github.com/rufeng0411/Nova-TradingAgent/releases)** · **[Collaborate](#collaborate)**

| Self-host | Docs | Collaborate |
| --- | --- | --- |
| SQLite + `uv` + built SPA on port **8000** | [install](docs/en/install.md) · [user guide](docs/en/user-guide.md) | WeChat **山君** |

```bash
git clone https://github.com/rufeng0411/Nova-TradingAgent.git
cd Nova-TradingAgent
cp .env.example .env          # Windows: Copy-Item .env.example .env
# fill TA_ADMIN_PASSWORD, TA_APP_SECRET_KEY, DATABASE_URL (see .env.example Quick start)
uv sync
cd frontend && npm install && npm run build && cd ..
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Health check: `GET http://127.0.0.1:8000/healthz`.

Not investment advice. Market data may be delayed.

## What the original project does not have

Upstream TradingAgents is a **multi-agent debate graph** (run a round from scripts or a notebook). **Nova-TradingAgent** is a self-hosted A-share **web desk**. The pages below are not in the original project — they are the point of this repo.

### 1. K-line workstation (ChartPro)

The original tree has **no** professional candlestick desk. This page is a full workstation: daily/weekly/monthly bars, adjust, MA + Bollinger, MACD golden/dead-cross labels, quote ribbon, **AI chart insight**; time-share / five-level book are entitlement-gated. It is not a broker order ticket.

<p align="center">
  <img src="assets/web/chartpro.png" width="100%" alt="ChartPro: SSE daily K-line, MA/Bollinger, MACD crosses, quote ribbon">
</p>

Sidebar **K-line** → `/chart`. Guide: [user-guide.md §4](docs/en/user-guide.md).

### 2. Fast analysis

The original tree has **no** two-minute short path. Here: snapshot features (60-day daily bars, RT daily, auction, …) → ~22 feature slots → **one LLM pass**, a conclusion card — not a full 15-agent debate. Default `TA_FAST_ANALYSIS_ENABLED=0`.

<p align="center">
  <img src="assets/web/fast-analysis.png" width="100%" alt="Fast analysis: two-minute decision aid, symbol and risk profile">
</p>

Sidebar **Fast analysis** → `/analysis/fast`. Guide: [user-guide.md §3](docs/en/user-guide.md).

### 3. Fifteen agents, translation layer, optional L2

- **Volume-price analyst** is in the default graph (15 nodes, not the old “14”).
- **Translation layer:** models read conclusions, not raw vendor dumps.
- **Tushare L2 order queue** is opt-in (`TA_TUSHARE_L2_ENABLED=0`). Empty book on missing permission; smart analysis still finishes.

### 4. Web smart analysis (canvas + debate + report)

Upstream mostly runs the graph in a terminal. Here you get a workflow canvas, debate drawer, and structured reports. The in-page quote strip is also this product, not the original CLI.

<p align="center">
  <img src="assets/web/analysis.png" width="100%" alt="Smart analysis: chat submit, 15-agent canvas, embedded chart">
</p>

<p align="center">
  <img src="assets/web/debate_drawer.png" width="90%" alt="Bull/bear and risk debate drawer, streamed by round">
</p>

<p align="center">
  <img src="assets/web/detail.png" width="48%" alt="Structured report and decision card">
  <img src="assets/web/reports.png" width="48%" alt="Report history">
</p>

### 5. Watchlist schedules, tracking board, login/admin

The original project has no scheduled watchlist jobs, position tracking board, or credits/plans/admin. Those ship in this tree.

<p align="center">
  <img src="assets/web/timer_analysis.png" width="70%" alt="Scheduled analysis on watchlist names, overnight trading-day window">
  <img src="assets/web/settings.png" width="28%" alt="Settings: model vendor and API key">
</p>

The Qlib bridge defaults off and is **not in the Docker image**. No fake screenshots.

## How the desk works

<p align="center">
  <img src="assets/schema.png" width="100%" alt="Fifteen-agent research graph">
</p>

Default graph: market, social, news, fundamentals, macro, smart money, volume-price, plus bull/bear researchers, research manager, trader, three risk roles, and the risk judge.

## Install

Follow **[docs/en/install.md](docs/en/install.md)**. Recommended: SQLite, build the frontend from source, run `uvicorn` on **8000**. Electron / MySQL, Vite 5173, and API 8001 are a separate local-dev setup — don’t mix them with this path.

The Docker image is published to `ghcr.io/rufeng0411/Nova-TradingAgent` when a `v*` tag is pushed. Until that build exists, `docker pull :latest` will fail; use the source install.

The image does not include Qlib.

## Configure (shallow)

Required for a clean boot: admin password, `TA_APP_SECRET_KEY` (≥32 bytes), SQLite URL under `data/`. Optional: `TA_API_KEY`, `TUSHARE_TOKEN`. See **[docs/en/configure.md](docs/en/configure.md)** and the Quick start block in `.env.example`.

## Docs

- [Install](docs/en/install.md) · [安装](docs/zh-CN/install.md)
- [User guide](docs/en/user-guide.md) · [使用手册](docs/zh-CN/user-guide.md)
- [Troubleshooting](docs/en/troubleshooting.md)
- [Configure](docs/en/configure.md)
- [Capabilities](docs/en/capabilities.md)
- [FAQ](docs/en/faq.md)

## Self-host notes (credits / admin)

First boot creates `admin` / `admin@localhost` from `TA_ADMIN_*`. Golden path sets `TA_ALLOW_REGISTRATION=0` so the empty database has only that administrator. Credits, plans, and `/admin` are included; they are for operators of this instance, not a hosted billing promise.

## Collaborate

Business and partnership: add WeChat **山君** (scan the QR). This is for collaboration, not only bug reports.

<p align="center">
  <img src="assets/community/wechat-contact.png" width="280" alt="WeChat: 山君">
</p>

Issues: use GitHub templates. Do not paste API keys.

## License

GNU Affero General Public License v3.0. If you modify this software and provide it over a network, you must offer the corresponding source to your users. See [LICENSE](LICENSE), [NOTICE](NOTICE), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Disclaimer

- **Not investment advice.** Output is algorithmic research, not a recommendation to buy or sell.
- **Data may be delayed or incomplete.** Exchange filings and your broker remain authoritative.
- No claim of guaranteed profit.
