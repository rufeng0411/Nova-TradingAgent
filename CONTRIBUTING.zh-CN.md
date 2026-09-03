# 贡献指南

较大改动请**先开 Issue / Discussion 再写大 PR**。错别字类文档可直接提 PR。

1. Fork 并克隆 `https://github.com/rufeng0411/Nova-TradingAgent.git`
2. 按 [docs/zh-CN/install.md](docs/zh-CN/install.md) 用 SQLite 拉起（端口 8000，`GET /healthz`）
3. 优先跑 `tests/` 里的无网络用例，不要拿生产密钥做 live E2E
4. 向 `main` 开 PR，提交信息使用 Conventional Commits

**不要**在 Issue、PR 或截图里粘贴 API Key、Tushare token 或 `.env`。
