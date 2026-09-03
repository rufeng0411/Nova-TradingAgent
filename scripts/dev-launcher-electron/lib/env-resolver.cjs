/**
 * 读取仓库根 .env（不打印密钥），解析 API 端口与 DATABASE_URL。
 */
const fs = require('fs');
const path = require('path');

function parseDotEnv(content) {
  const out = {};
  for (const line of content.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq <= 0) continue;
    const key = t.slice(0, eq).trim();
    let val = t.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}

function loadEnv(rootDir) {
  const p = path.join(rootDir, '.env');
  let file = {};
  try {
    if (fs.existsSync(p)) {
      file = parseDotEnv(fs.readFileSync(p, 'utf8'));
    }
  } catch (_) {}

  const merged = { ...file };
  const apiPort = Number(merged.TA_DEV_API_PORT || merged.PORT || process.env.TA_DEV_API_PORT || process.env.PORT || 8001);
  const databaseUrl =
    merged.DATABASE_URL ||
    process.env.DATABASE_URL ||
    'sqlite:///./tradingagents.db';

  return {
    rootDir,
    apiPort: Number.isFinite(apiPort) ? apiPort : 8001,
    databaseUrl,
    merged,
  };
}

function envForApiChild(baseEnv, apiPort) {
  return {
    ...baseEnv,
    TA_DEV_API_PORT: String(apiPort),
    PORT: String(apiPort),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
  };
}

module.exports = { loadEnv, envForApiChild, parseDotEnv };
