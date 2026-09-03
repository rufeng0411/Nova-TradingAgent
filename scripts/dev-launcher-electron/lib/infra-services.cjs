/**
 * 本机 PostgreSQL / Redis：状态探测与重启（Windows 为主；供 Electron 启动器 IPC）。
 */
const fs = require('fs');
const path = require('path');
const { execFile, spawn } = require('child_process');
const {
  tcpReachable,
  tryParseUrlAsHttp,
  resolvePostgresPaths,
  pgCtlStatus,
  envGet,
} = require('./datastore-probe.cjs');

function fileExists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function execFilePromise(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { windowsHide: true, maxBuffer: 2 * 1024 * 1024, ...opts }, (err, stdout, stderr) => {
      const code = err && typeof err.code === 'number' ? err.code : err ? 1 : 0;
      resolve({
        code,
        err,
        stdout: String(stdout || ''),
        stderr: String(stderr || ''),
      });
    });
  });
}

function parseRedisUrl(url) {
  const s = String(url || '').trim();
  if (!s) return { host: '127.0.0.1', port: 6379 };
  try {
    const u = new URL(s);
    const port = u.port ? Number(u.port) : 6379;
    const host = u.hostname || '127.0.0.1';
    return { host, port: Number.isFinite(port) ? port : 6379 };
  } catch {
    return { host: '127.0.0.1', port: 6379 };
  }
}

/** @param {Record<string, string>} merged */
function resolveRedisServer(merged) {
  const direct = envGet('TA_REDIS_SERVER_PATH', merged);
  if (direct && fileExists(direct)) {
    return { exe: direct, home: path.dirname(direct), label: direct };
  }
  const home = envGet('TA_REDIS_HOME', merged);
  const candidates = [];
  if (home) {
    candidates.push(path.join(home, 'redis-server.exe'));
    candidates.push(path.join(home, 'bin', 'redis-server.exe'));
  }
  candidates.push('D:\\pgsql\\redis\\redis-server.exe');
  for (const c of candidates) {
    if (fileExists(c)) return { exe: c, home: path.dirname(c), label: c };
  }
  return null;
}

function resolveRedisConf(merged, serverHome) {
  const explicit = envGet('TA_REDIS_CONF', merged);
  if (explicit && fileExists(explicit)) return explicit;
  const tryNames = ['redis.windows.conf', 'redis.conf', 'redis.windows-service.conf'];
  for (const n of tryNames) {
    const p = path.join(serverHome, n);
    if (fileExists(p)) return p;
  }
  return null;
}

function postgresListenTarget(merged) {
  const uri = String(merged.LANGGRAPH_POSTGRES_URI || '').trim();
  const p = tryParseUrlAsHttp(uri);
  if (p && p.host && Number.isFinite(p.port)) return { host: p.host, port: p.port };
  return { host: '127.0.0.1', port: 5432 };
}

/** Windows：结束监听指定端口的进程（与 port-claim 思路一致，单端口） */
function killListenersOnPortWin(port) {
  if (process.platform !== 'win32') return Promise.resolve();
  const ps =
    "$ErrorActionPreference='SilentlyContinue'; " +
    `$p=${Number(port)}; ` +
    '$conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; ' +
    'if ($null -eq $conns) { exit 0 }; ' +
    'foreach ($c in @($conns)) { ' +
    '$id=[int]$c.OwningProcess; ' +
    'if ($id -gt 4) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } ' +
    '}; exit 0';
  return new Promise((resolve) => {
    execFile('powershell.exe', ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], { windowsHide: true }, () => resolve());
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * @param {string} rootDir
 * @param {Record<string, string>} merged
 */
async function getInfraServicesStatus(rootDir, merged) {
  const pgPaths = resolvePostgresPaths(rootDir, merged);
  const { host: pgHost, port: pgPort } = postgresListenTarget(merged);
  let pgCtl = null;
  if (pgPaths) {
    pgCtl = await pgCtlStatus(pgPaths.pgCtl, pgPaths.dataDir);
  }
  const pgTcp = await tcpReachable(pgHost, pgPort, 1800);
  const redisUrl = merged.REDIS_URL || '';
  const { host: rh, port: rport } = parseRedisUrl(redisUrl);
  const redisTcp = await tcpReachable(rh, rport, 1500);
  const redisBin = resolveRedisServer(merged);

  return {
    postgres: {
      configured: !!pgPaths,
      home: pgPaths ? pgPaths.postgresHome : '',
      dataDir: pgPaths ? pgPaths.dataDir : '',
      pgCtlRunning: pgCtl ? pgCtl.running : null,
      tcpListen: pgTcp,
      probeHost: pgHost,
      probePort: pgPort,
      summary: pgPaths
        ? `${pgCtl && pgCtl.running ? 'pg_ctl:运行中' : 'pg_ctl:未运行'}；TCP ${pgHost}:${pgPort} ${pgTcp ? '可连' : '不可连'}`
        : `未解析到本机安装（配置 TA_POSTGRES_HOME 如 D:\\pgsql）；TCP ${pgHost}:${pgPort} ${pgTcp ? '可连' : '不可连'}`,
    },
    redis: {
      configured: !!redisBin,
      exe: redisBin ? redisBin.label : '',
      tcpListen: redisTcp,
      probeHost: rh,
      probePort: rport,
      urlPreview: !redisUrl
        ? '（未配置 REDIS_URL）'
        : redisUrl.length > 88
          ? `${redisUrl.slice(0, 88)}…`
          : redisUrl,
      summary: redisBin
        ? `可执行: ${redisBin.exe}；TCP ${rh}:${rport} ${redisTcp ? '可连' : '不可连'}`
        : `未找到 redis-server.exe（配置 TA_REDIS_HOME 如 D:\\pgsql\\redis）；TCP ${rh}:${rport} ${redisTcp ? '可连' : '不可连'}`,
    },
  };
}

/**
 * @param {string} rootDir
 * @param {Record<string, string>} merged
 * @param {(msg: string, kind?: string) => void} emit
 */
async function restartPostgres(rootDir, merged, emit) {
  const paths = resolvePostgresPaths(rootDir, merged);
  if (!paths) {
    const msg = '未找到本机 Postgres（检查 TA_POSTGRES_HOME / TA_POSTGRES_DATA / data\\PG_VERSION）';
    if (emit) emit(msg, 'err');
    return { ok: false, message: msg };
  }
  const { host, port } = postgresListenTarget(merged);
  const logFile = path.join(rootDir, 'logs', 'postgres-pg_ctl-launcher.log');
  try {
    if (!fs.existsSync(path.dirname(logFile))) fs.mkdirSync(path.dirname(logFile), { recursive: true });
  } catch (_) {}

  if (emit) emit(`[本机] PostgreSQL 重启: ${paths.pgCtl} -D ${paths.dataDir}`, 'accent');
  let r = await execFilePromise(paths.pgCtl, ['-D', paths.dataDir, 'restart', '-w', '-t', '120', '-l', logFile]);
  if (r.code !== 0) {
    if (emit) emit(`[本机] pg_ctl restart 非零(${r.code})，尝试 stop + start…`, 'warn');
    await execFilePromise(paths.pgCtl, ['-D', paths.dataDir, 'stop', '-m', 'fast', '-w', '-t', '60']);
    await sleep(600);
    r = await execFilePromise(paths.pgCtl, [
      '-D',
      paths.dataDir,
      '-l',
      logFile,
      'start',
      '-w',
      '-t',
      '120',
      '-o',
      `-p${port}`,
    ]);
  }
  const out = `${r.stdout}\n${r.stderr}`.trim();
  if (out && emit) emit(out, r.code !== 0 ? 'err' : 'line');
  const ok = await tcpReachable(host, port, 5000);
  if (emit) emit(ok ? `[本机] PostgreSQL 已监听 ${host}:${port}` : `[本机] 重启后 TCP 仍不可达 ${host}:${port}，见 ${logFile}`, ok ? 'ok' : 'err');
  return { ok, message: ok ? 'PostgreSQL 已就绪' : 'PostgreSQL 重启后端口仍不可达' };
}

/**
 * @param {Record<string, string>} merged
 * @param {(msg: string, kind?: string) => void} emit
 */
async function restartRedis(merged, emit) {
  const { host, port } = parseRedisUrl(merged.REDIS_URL || '');
  const bin = resolveRedisServer(merged);
  if (!bin) {
    const msg = '未找到 redis-server.exe（设置 TA_REDIS_HOME=D:\\pgsql\\redis 或 TA_REDIS_SERVER_PATH）';
    if (emit) emit(msg, 'err');
    return { ok: false, message: msg };
  }
  const conf = resolveRedisConf(merged, bin.home);
  if (emit) emit(`[本机] Redis 重启: 释放端口 ${port} 后启动 ${bin.exe}`, 'accent');
  if (process.platform === 'win32') {
    await killListenersOnPortWin(port);
  }
  await sleep(500);
  const args = conf ? [conf] : ['--port', String(port)];
  const cwd = bin.home;
  const child = spawn(bin.exe, args, {
    cwd,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    shell: false,
  });
  child.unref();
  await sleep(800);
  const ok = await tcpReachable(host, port, 4000);
  if (emit) emit(ok ? `[本机] Redis 已监听 ${host}:${port}` : `[本机] Redis 启动后 TCP 仍不可达`, ok ? 'ok' : 'warn');
  return { ok, message: ok ? 'Redis 已就绪' : '已尝试启动，端口仍不可达（检查配置/权限）' };
}

/**
 * 智能一键前：若配置了 REDIS_URL 且端口不可达，尝试拉起本机 redis-server。
 * @param {Record<string, string>} merged
 * @param {(msg: string, kind?: string) => void} emit
 */
async function ensureRedisAsync(merged, emit) {
  const url = String(merged.REDIS_URL || '').trim();
  if (!url) {
    if (emit) emit('[数据] 未配置 REDIS_URL，跳过 Redis 自动启动', 'muted');
    return { attempted: false, ok: true, skipped: true };
  }
  const { host, port } = parseRedisUrl(url);
  if (await tcpReachable(host, port, 1500)) {
    if (emit) emit(`[数据] Redis 已可达 ${host}:${port}`, 'muted');
    return { attempted: false, ok: true, already: true };
  }
  const bin = resolveRedisServer(merged);
  if (!bin) {
    if (emit) emit('[数据] Redis 不可达且未找到 redis-server.exe（可设 TA_REDIS_HOME）', 'warn');
    return { attempted: false, ok: false };
  }
  if (emit) emit(`[数据] 尝试启动 Redis: ${bin.exe}`, 'warn');
  return restartRedis(merged, emit);
}

module.exports = {
  getInfraServicesStatus,
  restartPostgres,
  restartRedis,
  ensureRedisAsync,
  parseRedisUrl,
  resolveRedisServer,
};
