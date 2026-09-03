@echo off
REM 启动 dev 模式 API（不带 --reload，避免 Windows 下 reload watcher 把 worker 派发到 sys._base_executable 导致依赖找不到）
cd /d "F:\Ai-tradingagents-A-1"
"F:\Ai-tradingagents-A-1\.venv\Scripts\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8001 > "F:\Ai-tradingagents-A-1\logs\uvicorn.out.log" 2> "F:\Ai-tradingagents-A-1\logs\uvicorn.err.log"
