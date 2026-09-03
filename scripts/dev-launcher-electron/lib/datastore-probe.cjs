/**
 * 开发启动器：探测 MySQL / LangGraph Postgres 可达性；必要时尝试 pg_ctl 拉起本机 Postgres。
 */
const fs = require('fs');
const path = require('path');
const net = require('net');
const { execFile } = require('child_process');

function tcpReachable(host, port, timeoutMs = 2200) {
  return new Promise((resolve) => {
    const sock = net.createConnection({ host, port }, () => {
      sock.end();
      resolve(true);
    });
    sock.setTimeout(timeoutMs, () => {
      sock.destroy();
      resolve(false);
    });
    sock.on('error', () => resolve(false));
  });
}

/** @param {(msg: string, kind?: string) => void} emit */
function emitLine(emit, msg, kind = 'muted') {
  if (typeof emit === 'function') emit(msg, kind);
}

function safeDecode(s) {
  try {
    return decodeURIComponent(s || '');
  } catch {
    return s || '';
  }
}

function tryParseUrlAsHttp(dbUrl) {
  const s = String(dbUrl || '').trim();
  if (!s) return null;
  let fake = s;
  if (/^mysql\+pymysql:\/\//i.test(fake)) fake = 'http://' + fake.slice('mysql+pymysql://'.length);
  else if (/^mysql:\/\//i.test(fake)) fake = 'http://' + fake.slice('mysql://'.length);
  else if (/^postgresql(\+[^:]+)?:\/\//i.test(fake)) {
    fake = fake.replace(/^postgresql(\+[^:]+)?:\/\//i, 'http://');
  } else return null;
  try {
    const u = new URL(fake);
    const host = u.hostname || '127.0.0.1';
    let port = u.port ? Number(u.port) : NaN;
    if (!Number.isFinite(port)) {
      if (/^mysql/i.test(s)) port = 3306;
      else port = 5432;
    }
    const user = safeDecode(u.username || '');
    const password = safeDecode(u.password || '');
    const db = (u.pathname || '').replace(/^\//, '').split(/[?]/)[0] || '';
    return { host, port, user, password, database: db };
  } catch {
    return null;
  }
}

function maskDbUrlPreview(raw) {
  const s = String(raw || '').trim();
  const p = tryParseUrlAsHttp(s);
  if (!p) return s.length > 96 ? `${s.slice(0, 96)}…` : s;
  const auth = p.user ? `${p.user}:***@` : '';
  const base = s.split('://')[0] || 'db';
  return `${base}://${auth}${p.host}:${p.port}/${p.database}`;
}

function fileExists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function envGet(key, merged) {
  if (merged && merged[key] != null && String(merged[key]).trim() !== '') return String(merged[key]).trim();
  const v = process.env[key];
  return v ? String(v).trim() : '';
}

/** @param {Record<string, string>} [merged] 来自仓库根 .env 的合并项（Electron 主进程未必已注入 process.env） */
function resolvePostgresPaths(rootDir, merged = {}) {
  const home = envGet('TA_POSTGRES_HOME', merged) || envGet('PG_HOME', merged);
  const roots = [];
  if (home) roots.push(home);
  roots.push('D:\\pgsql', 'C:\\pgsql');
  for (const r of roots) {
    const pgCtl = path.join(r, 'bin', 'pg_ctl.exe');
    const psql = path.join(r, 'bin', 'psql.exe');
    const data = envGet('TA_POSTGRES_DATA', merged) || path.join(r, 'data');
    if (fileExists(pgCtl) && fileExists(path.join(data, 'PG_VERSION'))) {
      return { postgresHome: r, pgCtl, psql, dataDir: data };
    }
  }
  const pgCtlEnv = envGet('TA_PGCTL_PATH', merged) || envGet('TA_PG_CTL', merged);
  if (pgCtlEnv && fileExists(pgCtlEnv)) {
    const bin = path.dirname(pgCtlEnv);
    const psql = path.join(bin, 'psql.exe');
    const data = envGet('TA_POSTGRES_DATA', merged);
    if (data && fileExists(path.join(data, 'PG_VERSION'))) {
      return { postgresHome: bin, pgCtl: pgCtlEnv, psql, dataDir: data };
    }
  }
  return null;
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

async function pgCtlStatus(pgCtl, dataDir) {
  const r = await execFilePromise(pgCtl, ['-D', dataDir, 'status']);
  const out = `${r.stdout}\n${r.stderr}`.trim();
  const running = r.code === 0 && /server is running/i.test(out);
  return { running, out, code: r.code };
}

/**
 * @returns {Promise<{ mode: string, uriPreview?: string, host?: string, port?: number, database?: string, tcpOk: boolean, psqlOk: boolean, pgRunning?: boolean|null, summary: string, detail?: string }>}
 */
async function probeLanggraphPostgres(rootDir, uri, merged = {}) {
  const mode = 'postgres';
  const uriPreview = maskDbUrlPreview(uri);
  const p = tryParseUrlAsHttp(uri);
  if (!p || !p.host) {
    return {
      mode,
      uriPreview,
      tcpOk: false,
      psqlOk: false,
      summary: '无法解析 LANGGRAPH_POSTGRES_URI',
      detail: '检查 .env 中连接串格式',
    };
  }
  const tcpOk = await tcpReachable(p.host, p.port);
  let psqlOk = false;
  let pgRunning = null;
  const paths = resolvePostgresPaths(rootDir, merged);
  if (paths) {
    const st = await pgCtlStatus(paths.pgCtl, paths.dataDir);
    pgRunning = st.running;
  }
  const psqlBin =
    envGet('TA_PSQL_PATH', merged) ||
    (paths && fileExists(paths.psql) ? paths.psql : 'psql');
  if (tcpOk && p.user) {
    const env = { ...process.env, PGPASSWORD: p.password || '' };
    const r = await execFilePromise(
      psqlBin,
      ['-h', p.host, '-p', String(p.port), '-U', p.user, '-d', p.database || 'postgres', '-tAc', 'SELECT 1'],
      { env, timeout: 8000 }
    );
    psqlOk = /^\s*1\s*$/m.test(r.stdout) && !r.err;
  }
  let summary = '';
  if (tcpOk && psqlOk) summary = '端口可达且认证通过';
  else if (tcpOk) summary = '端口可达，psql 认证未通过（检查口令/用户/库）';
  else if (pgRunning === false) summary = '端口不可达，本机 pg_ctl 显示未运行';
  else if (pgRunning === true) summary = '端口不可达但数据目录显示运行中（核对端口/防火墙）';
  else summary = '端口不可达（未找到本机 pg_ctl 或未配置数据目录）';

  return {
    mode,
    uriPreview,
    host: p.host,
    port: p.port,
    database: p.database,
    tcpOk,
    psqlOk,
    pgRunning,
    summary,
  };
}

/**
 * @returns {Promise<{ enabled: boolean, host?: string, port?: number, tcpOk: boolean, summary: string }>}
 */
async function probeMysql(databaseUrl) {
  if (!/^mysql/i.test(String(databaseUrl || ''))) {
    return { enabled: false, tcpOk: false, summary: '（当前 DATABASE_URL 非 MySQL）' };
  }
  const p = tryParseUrlAsHttp(databaseUrl);
  if (!p) return { enabled: true, tcpOk: false, summary: '无法解析 MySQL URL' };
  const tcpOk = await tcpReachable(p.host, p.port);
  return {
    enabled: true,
    host: p.host,
    port: p.port,
    tcpOk,
    summary: tcpOk ? `TCP ${p.host}:${p.port} 可达` : `TCP ${p.host}:${p.port} 不可达（mysqld 未启动或端口错误）`,
  };
}

/**
 * 智能一键 / 重启前：本机 Postgres（便携安装如 D:\\pgsql）若端口未监听则尝试 pg_ctl start。
 * - LANGGRAPH_CHECKPOINTER=postgres 且配置了 LANGGRAPH_POSTGRES_URI 时必尝试（URI 指向本机时）。
 * - 另：若 LANGGRAPH_POSTGRES_URI 指向 127.0.0.1/localhost 且未设置 TA_DEV_POSTGRES_AUTOSTART=0，也会尝试拉起，
 *   便于 LangGraph 用 PG 而 MARKETDATA 等也连同一实例的开发机（用户要求「与 API 一块启动」）。
 */
async function ensureLanggraphPostgresAsync(rootDir, mergedEnv, emit) {
  const mode = String(mergedEnv.LANGGRAPH_CHECKPOINTER || 'sqlite').toLowerCase();
  const uri = String(mergedEnv.LANGGRAPH_POSTGRES_URI || '').trim();
  const autoStart = String(mergedEnv.TA_DEV_POSTGRES_AUTOSTART || '1').trim() !== '0';

  if (mode === 'postgres' && !uri) {
    emitLine(emit, '[数据] LANGGRAPH_CHECKPOINTER=postgres 但 LANGGRAPH_POSTGRES_URI 为空', 'err');
    return { attempted: false, started: false };
  }
  if (!uri) {
    emitLine(emit, '[数据] 无 LANGGRAPH_POSTGRES_URI（跳过本机 Postgres 自动启动）', 'muted');
    return { attempted: false, started: false };
  }
  const p = tryParseUrlAsHttp(uri);
  if (!p) {
    emitLine(emit, '[数据] 无法解析 LANGGRAPH_POSTGRES_URI', 'err');
    return { attempted: false, started: false };
  }
  const localHost =
    p.host === '127.0.0.1' || p.host === 'localhost' || p.host === '::1';
  /** 仅对本机 URI 调 pg_ctl；远端库只探测不启动 */
  const shouldTryPgCtl = localHost && (mode === 'postgres' || autoStart);

  if (!shouldTryPgCtl) {
    if (mode === 'postgres') {
      emitLine(emit, `[数据] LangGraph Postgres 为远端 ${p.host}，本机 pg_ctl 不启动`, 'muted');
    } else {
      emitLine(
        emit,
        `[数据] LangGraph 模式 ${mode}；LANGGRAPH_POSTGRES_URI 非本机或已 TA_DEV_POSTGRES_AUTOSTART=0（跳过本机 Postgres）`,
        'muted'
      );
    }
    return { attempted: false, started: false };
  }

  if (await tcpReachable(p.host, p.port, 1500)) {
    emitLine(emit, `[数据] Postgres 已可达 ${p.host}:${p.port}`, 'muted');
    return { attempted: false, started: false, already: true };
  }
  const paths = resolvePostgresPaths(rootDir, mergedEnv);
  if (!paths) {
    emitLine(
      emit,
      '[数据] Postgres 不可达且未找到本机 pg_ctl（可设置 TA_POSTGRES_HOME 如 D:\\pgsql，或 TA_PGCTL_PATH + TA_POSTGRES_DATA）',
      'warn'
    );
    return { attempted: false, started: false };
  }
  emitLine(emit, `[数据] 尝试启动 Postgres: ${paths.pgCtl} -D ${paths.dataDir}（对外端口 ${p.port}）`, 'warn');
  const logFile = path.join(rootDir, 'logs', 'postgres-pg_ctl-launcher.log');
  try {
    if (!fs.existsSync(path.dirname(logFile))) fs.mkdirSync(path.dirname(logFile), { recursive: true });
  } catch (_) {}
  const st = await pgCtlStatus(paths.pgCtl, paths.dataDir);
  if (st.running) {
    emitLine(emit, '[数据] pg_ctl 报告已在运行，但探测端口仍不可达；请核对 postgresql.conf port 与 LANGGRAPH_POSTGRES_URI 是否一致', 'warn');
    return { attempted: true, started: false };
  }
  // Windows 下 -o 须为传给 postgres 的**单个**参数字符串，否则 -p 可能被误解析为 pg_ctl 的选项
  const start = await execFilePromise(paths.pgCtl, [
    '-D',
    paths.dataDir,
    '-l',
    logFile,
    'start',
    '-w',
    '-t',
    '120',
    '-o',
    `-p${p.port}`,
  ]);
  const combined = `${start.stdout}\n${start.stderr}`.trim();
  if (combined) emitLine(emit, combined, start.code !== 0 ? 'err' : 'line');
  const ok = await tcpReachable(p.host, p.port, 4000);
  if (ok) emitLine(emit, `[数据] Postgres 已启动并可连 ${p.host}:${p.port}`, 'ok');
  else emitLine(emit, '[数据] pg_ctl start 后端口仍不可达，请查看 logs/postgres-pg_ctl-launcher.log', 'err');
  return { attempted: true, started: ok };
}

/**
 * @param {(msg: string, kind?: string) => void} emit
 */
async function preflightMysqlTcp(databaseUrl, emit) {
  const r = await probeMysql(databaseUrl);
  if (!r.enabled) return r;
  emitLine(emit, `[数据] MySQL(业务): ${r.summary}`, r.tcpOk ? 'muted' : 'warn');
  return r;
}

module.exports = {
  tcpReachable,
  tryParseUrlAsHttp,
  maskDbUrlPreview,
  probeMysql,
  probeLanggraphPostgres,
  ensureLanggraphPostgresAsync,
  preflightMysqlTcp,
  resolvePostgresPaths,
  pgCtlStatus,
  envGet,
};
