# Capabilities

One page: **what we kept from the upstream debate graph**, and **what this repo adds**. No directory tree, no internals, no second-development roadmap.

## One sentence

Self-hosted A-share research desk: fifteen agents debate into a structured report; ChartPro and fast analysis cover the tape and a short take; a translation layer distills data before the model; L2 / Qlib / multi-user credits and admin turn on when you have the entitlement and the ops need. No orders by default.

## Inherited

Seven analysts (market, social, news, fundamentals, macro, smart money, **volume-price**) → bull/bear debate → research manager → trader → three risk voices → risk judge. The web canvas and debate drawer make that graph visible and reviewable.

## Translation layer

Market, financial, and flow data become **conclusions and evidence** before the model sees them. A missing vendor degrades that slot; the job still finishes.

## Web workbench (pages the original project does not have)

One FastAPI process; built SPA on port **8000**:

- **K-line** ChartPro (`/chart`): workstation + AI insight — `assets/web/chartpro.png`
- **Fast analysis** (`/analysis/fast`): ~2-minute single LLM pass — `assets/web/fast-analysis.png`
- Smart-analysis canvas / debate drawer / reports — `assets/web/analysis.png` and siblings
- Watchlist schedules, tracking board, Settings

## L2 ingest (not in the original project)

Tushare **order-queue / book pressure** as a product flag, default off (`TA_TUSHARE_L2_ENABLED=0`). Covers hanging-order thickness daily bars cannot. Needs a separate L2 entitlement; empty slot without it; analysis continues. No fake empty-book screenshot; marks in the README: `assets/web/tushare.svg` and `l2-orderqueue.svg`.

## Qlib integration (not in the original project)

Isolated `QLIB/` workspace + inbox/outbox file bridge. Main process must not `import qlib`. All `TA_QLIB_*` flags default 0. **Not in Docker.** For operators who already have Qlib data. Mark: `assets/web/qlib-logo.png`.

## Multi-user subscriptions (not in the original project)

Accounts, credits, Free/Pro/Team requests (admin review), ledger. Sidebar **Subscription** `/subscription` — `assets/web/subscription.png`. Quotas for this instance, not a hosted billing SLA.

## Admin console (not in the original project)

`/admin`: reports, plans and orders, credit ledger, API cost, tasks and LLM logs, audit, users. Shots: `assets/web/admin.png`, `admin-users.png`.
