# Capabilities

One page on what the desk is strong at. No directory tree, no data-flow internals, no second-development roadmap.

## 15-agent loop

Seven analysts (market, social, news, fundamentals, macro, smart money, volume-price) → bull/bear debate → research manager → trader → three risk voices → risk judge. The web canvas and debate drawer make the loop visible.

## Translation layer

Market, financial, and flow data are reduced to **conclusions and evidence** before the model sees them. Missing a vendor degrades softly instead of aborting the whole job.

## Optional L2

Tushare order-queue / book pressure is **opt-in** (`TA_TUSHARE_L2_ENABLED=0`). Needs a separate entitlement. Empty UI on missing permission; smart analysis continues.

## Optional Qlib bridge

Eval sandbox flags default off. **Not packaged in Docker.** For operators who already have Qlib data locally.

## Web workbench (pages the original project does not have)

One FastAPI process. Extra vs the upstream debate graph:

- **K-line** ChartPro (`/chart`): workstation + AI insight — README shot `assets/web/chartpro.png`
- **Fast analysis** (`/analysis/fast`): ~2-minute short path — `assets/web/fast-analysis.png`
- Smart-analysis canvas / debate drawer / reports: `assets/web/analysis.png` and siblings
- Watchlist schedules, tracking board, login/credits, admin

Golden path: build the SPA, serve it on port **8000**.
