# User guide

Feature-by-feature against the real sidebar. Each section: **entry, prerequisites, steps, expected UI, failures**. Install: [install.md](install.md). Business contact: README **Collaborate** (WeChat **山君**).

This is a research desk. It does **not** place orders by default. Not investment advice. Data may be delayed.

Terms: smart analysis / fast analysis / K-line analysis / credits / L2 order queue (opt-in) / Qlib bridge.

---

## 1. Login / password / account & credits

**Entry:** `http://127.0.0.1:8000` → `/login`. After login, **Account** (`/account`). Header avatar: logout; admins can open `/admin`.

**Prereq:** App running. Default admin `admin` / `TA_ADMIN_PASSWORD` (example `ChangeMe_Admin1!`). With `TA_ALLOW_REGISTRATION=0` there is no public sign-up.

**Steps:** Sign in; open Account; change password (letter+digit, min 8); read credits; create an API token (plaintext shown once).

**Expect:** Sidebar (Dashboard, Smart analysis, Fast analysis, K-line, …). Credits visible.

**Fail:** “Cannot reach backend” → use port **8000**. Bad password → `.env` or `uv run python scripts/reset_admin_password.py`.

---

## 2. Smart analysis

**Entry:** **智能分析** → `/analysis`.

**Prereq:** `TA_API_KEY` or a key saved in Settings; `TUSHARE_TOKEN` recommended. Credits: `TA_COST_ANALYSIS`. 402 if balance is too low.

**Steps:** Type natural language in the **left chat** (e.g. “调研贵州茅台短线” or `600519.SH`). Watch the **workflow canvas**. Click an agent card for the **debate drawer**. Read the **report** and **decision card**. Open the **data-source** dialog. Empty L2 fields are a soft failure if you did not opt in.

**Expect:** Fifteen-role graph (seven analysts including volume-price, bull/bear, manager, trader, three risk voices, judge).

**Fail:** No key → Settings or `.env` then restart.

Screens: `assets/web/analysis.png`, `debate_drawer.png`, `detail.png`.

---

## 3. Fast analysis

**Entry:** `/analysis/fast`.

**Prereq:** `TA_FAST_ANALYSIS_ENABLED=1` (example file defaults to 0). LLM required.

**Steps:** Enter a symbol, optional hint, risk profile; submit; read the conclusion card.

**Fail:** Feature off until the env flag is set and the API restarted.

---

## 4. K-line analysis

**Entry:** `/chart`.

**Prereq:** Market data token for candles. Intraday / five-level book needs `advanced_market` or `tushare_rt` (admins usually see advanced UI). AI insight needs an LLM.

**Steps:** Search a symbol; change period/adjust; start **Ai insight**. Without entitlements, book/intraday stay empty — expected.

This is not an exchange L2 terminal.

---

## 5. Watchlist & scheduled analysis

**Entry:** `/portfolio`.

Add symbols; enable **scheduled analysis**; batch edit/delete/test. Repeated failures auto-disable. See `assets/web/timer_analysis.png`.

---

## 6. Positions & tracking board

**Entry:** `/tracking-board`; imports also on the watchlist page. Screenshot import needs `TA_VLM_*`. **Realtime board:** `/realtime-board`.

---

## 7. Report history

**Entry:** `/reports`. Empty on a fresh database. See `assets/web/reports.png`.

---

## 8. Task center

**Entry:** `/tasks`. Requires `TA_USER_TASK_QUEUE_ENABLED` (on by default).

---

## 9. Settings (model providers)

**Entry:** `/settings`. Save vendor, key, model; warmup optional. Never paste keys into GitHub issues. See `assets/web/settings.png`.

---

## 10. Admin (browse-level)

**Entry:** `/admin` (admin role). Check **Users** is only your default admin on a clean DB. Browse plans; do not treat this as a hosted billing SLA.

---

## L2 order queue (opt-in)

Default `TA_TUSHARE_L2_ENABLED=0`. You need a Tushare L2 entitlement. Missing permission returns empty data; analysis continues.

---

## Qlib bridge (optional)

Flags default off. **Not in the Docker image.** See [capabilities.md](capabilities.md).
