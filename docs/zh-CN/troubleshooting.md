# 故障排除

## 页面空白

未执行 `cd frontend && npm install && npm run build`。API 只在存在 `frontend/dist` 时挂载 SPA。

## 连不上后端

黄金路径请打开 `http://127.0.0.1:8000`。不要用 Vite 5173，除非你同时跑了开发 API 8001。

## 健康检查失败

正确路径是 **`GET /healthz`**，不是 `/health`。

## 启动报 TA_ADMIN_PASSWORD

`.env` 必须有非空管理员口令（字母+数字、≥8）。在仓库根启动以便加载 `.env`。

## Docker pull 404

镜像随 `v*` tag 构建。未构建前请用源码安装。镜像不含 Qlib。

## L2 没有数据

默认关闭。无 Tushare L2 权限时为空，属预期。

## 分析立刻失败

未配置 LLM Key，或点数不足（402）。先在设置页保存 Key，确认账户点数。

## 端口占用

结束占用 8000 的进程，或改 uvicorn `--port` 并同步改浏览器地址。
