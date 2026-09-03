# Troubleshooting

## Blank page

You skipped `cd frontend && npm install && npm run build`. The API mounts the SPA only if `frontend/dist` exists.

## Cannot reach the API

Recommended URL is `http://127.0.0.1:8000`. Do not use Vite 5173 unless the dev API on 8001 is also running.

## Health check

Use **`GET /healthz`**, not `/health`.

## `TA_ADMIN_PASSWORD` on boot

Set a non-empty admin password (letters+digits, min 8) in `.env`. Start from the repo root so dotenv loads.

## Docker pull 404

Images build on `v*` tags. Use source install until then. The image has no Qlib.

## Empty L2

Off by default. Empty data without a Tushare L2 entitlement is expected.

## Analysis fails immediately

No LLM key, or not enough credits (402). Save a key in Settings and check the account balance.

## Port in use

Free port 8000 or change `--port` and the browser URL together.
