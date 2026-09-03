# 前端路由自动化核对

- 基准 URL: `https://app.510168.xyz`
- 时间: 2026-05-02T13:11:03.598Z
- 浏览器: Microsoft Edge (channel)
- 录屏: 未启用（设置 RECORD_VIDEO=1 且需 npx playwright install ffmpeg）

| # | 路由 | 最终 URL | 标题 | HTTP | 截图 |
|---|------|----------|------|------|------|
| 01-login | /login | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 01-login.png |
| 02-sponsor | /sponsor | https://app.510168.xyz/sponsor | TradingAgents Dashboard | 200 | 02-sponsor.png |
| 03-thanks | /thanks | https://app.510168.xyz/thanks | TradingAgents Dashboard | 200 | 03-thanks.png |
| 04-root | / | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 04-root.png |
| 05-analysis | /analysis | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 05-analysis.png |
| 06-reports | /reports | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 06-reports.png |
| 07-portfolio | /portfolio | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 07-portfolio.png |
| 08-tracking-board | /tracking-board | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 08-tracking-board.png |
| 09-feedback | /feedback | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 09-feedback.png |
| 10-settings | /settings | https://app.510168.xyz/login | TradingAgents Dashboard | 200 | 10-settings.png |

说明：未登录时受保护路由应重定向到 /login。