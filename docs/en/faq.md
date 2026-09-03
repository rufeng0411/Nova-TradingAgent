# FAQ

## What is this vs upstream TradingAgents?

A self-hosted A-share research desk: the original multi-agent debate graph (fifteen nodes, including volume-price), plus a web UI, ChartPro, fast analysis, a translation layer, optional Tushare L2, optional Qlib bridge, multi-user credits, and admin. No orders by default. See the README product overview.

## Is this an auto-trading bot?

No. It is a research desk. It does not place orders by default.

## Why not `/health`?

The health endpoint is `GET /healthz`.

## 14 or 15 agents?

**15** default graph nodes (including the volume-price analyst). Do not copy “14” from older upstream write-ups.

## Is Level-2 on out of the box?

No. `TA_TUSHARE_L2_ENABLED` defaults to 0 and needs a Tushare L2 / order-queue entitlement. Empty slot without it; analysis continues. The README uses vendor marks, not a fake empty book.

## Can I run Qlib backtests out of the box?

No. Qlib lives in isolated `QLIB/`, flags default off, **not in Docker**. You need local Qlib data and the file bridge in `QLIB/README.md`.

## Are subscriptions a hosted billing product?

No. Credits, plan requests, and `/admin` operate **your** instance, not a payment SLA from this repository.

## Is billing stripped for a community edition?

No. This tree is the full product (credits and admin included). Secrets and runtime databases are not in Git.

## Why AGPL?

If you modify this software and offer it over a network, you must provide the corresponding source to your users.

## Does Docker include Qlib?

No.

## Business contact?

WeChat **山君** — see README Collaborate.
