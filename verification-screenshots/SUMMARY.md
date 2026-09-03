# 前端路由自动化核对

- 基准 URL: `http://localhost:5175`
- 时间: 2026-05-02T13:10:29.999Z
- 浏览器: Microsoft Edge (channel)
- 录屏: 未启用（设置 RECORD_VIDEO=1 且需 npx playwright install ffmpeg）

| # | 路由 | 最终 URL | 标题 | HTTP | 截图 |
|---|------|----------|------|------|------|
| 01-login | /login | about:blank |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/login
Call log:
  - navigating to "http://localhost:5175/login", waiting until "domcontentloaded"
 |
| 02-sponsor | /sponsor | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/sponsor
Call log:
  - navigating to "http://localhost:5175/sponsor", waiting until "domcontentloaded"
 |
| 03-thanks | /thanks | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/thanks
Call log:
  - navigating to "http://localhost:5175/thanks", waiting until "domcontentloaded"
 |
| 04-root | / | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/
Call log:
  - navigating to "http://localhost:5175/", waiting until "domcontentloaded"
 |
| 05-analysis | /analysis | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/analysis
Call log:
  - navigating to "http://localhost:5175/analysis", waiting until "domcontentloaded"
 |
| 06-reports | /reports | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/reports
Call log:
  - navigating to "http://localhost:5175/reports", waiting until "domcontentloaded"
 |
| 07-portfolio | /portfolio | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/portfolio
Call log:
  - navigating to "http://localhost:5175/portfolio", waiting until "domcontentloaded"
 |
| 08-tracking-board | /tracking-board | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/tracking-board
Call log:
  - navigating to "http://localhost:5175/tracking-board", waiting until "domcontentloaded"
 |
| 09-feedback | /feedback | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/feedback
Call log:
  - navigating to "http://localhost:5175/feedback", waiting until "domcontentloaded"
 |
| 10-settings | /settings | chrome-error://chromewebdata/ |  | - | page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://localhost:5175/settings
Call log:
  - navigating to "http://localhost:5175/settings", waiting until "domcontentloaded"
 |

说明：未登录时受保护路由应重定向到 /login。