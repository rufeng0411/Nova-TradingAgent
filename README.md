# Nova-TradingAgent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md)

**Fifteen specialists. One A-share research desk.**

Self-hosted multi-agent research for China A-shares: 15-agent debate, optional Tushare Level-2 order queue, a K-line workstation with AI insight, and a signal translation layer so models read conclusions — not raw dumps.

This is a **research workbench**. It does **not** place trades by default.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/rufeng0411/Nova-TradingAgent)](https://github.com/rufeng0411/Nova-TradingAgent/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**[Install](docs/en/install.md)** · **[User guide](docs/en/user-guide.md)** · **[Releases](https://github.com/rufeng0411/Nova-TradingAgent/releases)** · **[Collaborate](#collaborate)**

There is **no** third-party hosted trial. Run **Nova-TradingAgent** yourself, or add WeChat **山君** for business.

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

## What's different

- **15-agent desk** — seven analysts (including volume-price), bull/bear debate, research manager, trader, three risk voices, risk judge.
- **Translation layer** — vendors and tables are reduced to conclusions the model can use, instead of dumping raw feeds into the prompt.
- **Optional Tushare L2** — off by default (`TA_TUSHARE_L2_ENABLED=0`). Needs a Tushare L2 entitlement. Missing permission returns empty data; analysis continues.
- **K-line workstation** — ChartPro with periods, quotes, and an AI insight panel (not a broker terminal).
- **Self-hosted SaaS surface** — login, credits, plans, and an admin console ship in this tree. Configure them; they are not a separate commercial cut.

## See it run

<p align="center">
  <img src="assets/web/analysis.png" width="100%" alt="Smart analysis canvas with multi-agent workflow">
</p>

<p align="center">
  <img src="assets/web/debate_drawer.png" width="90%" alt="Debate drawer during multi-agent research">
</p>

<p align="center">
  <img src="assets/web/detail.png" width="48%" alt="Structured research report">
  <img src="assets/web/reports.png" width="48%" alt="History of research reports">
</p>

<p align="center">
  <img src="assets/web/dashboard.png" width="48%" alt="Dashboard">
  <img src="assets/web/settings.png" width="48%" alt="Model provider settings">
</p>

K-line / Level-2 / Qlib screenshots: see the evaluation report if a local entitlement was not available at packaging time. Do not treat schema diagrams as live market UI.

## How the desk works

<p align="center">
  <img src="assets/schema.png" width="100%" alt="Fifteen-agent research graph">
</p>

Default graph: market, social, news, fundamentals, macro, smart money, volume-price, plus bull/bear researchers, research manager, trader, three risk roles, and the risk judge.

## Install

Strangers should follow **[docs/en/install.md](docs/en/install.md)** only. That path is SQLite + source build + `uvicorn` on **8000**. It is not the maintainer Electron + MySQL stack (Vite **5173** / API **8001**).

Docker images publish on the `v*` tag (`ghcr.io/rufeng0411/Nova-TradingAgent`). Until that workflow has run, `docker pull` of `:latest` will 404 — use source install.

Qlib is **not** inside the Docker image.

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
