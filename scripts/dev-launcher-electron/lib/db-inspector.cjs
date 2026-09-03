const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { probeMysql, probeLanggraphPostgres, maskDbUrlPreview } = require('./datastore-probe.cjs');

function resolveSqlitePath(databaseUrl, rootDir) {
  const u = databaseUrl.trim();
  if (!u.startsWith('sqlite:')) return null;
  let rest = u.replace(/^sqlite:\/\/\//, '').replace(/^sqlite:\/\//, '');
  if (!rest) return null;
  rest = rest.split('?')[0];
  if (rest.startsWith('./')) rest = path.join(rootDir, rest.slice(2));
  else if (!path.isAbsolute(rest)) rest = path.join(rootDir, rest);
  return path.normalize(rest);
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function tableCountPromise(dbPath) {
  return new Promise((resolve) => {
    execFile('sqlite3', [dbPath, "SELECT count(*) FROM sqlite_master WHERE type='table';"], { windowsHide: true }, (err, stdout) => {
      if (err) return resolve(null);
      const n = parseInt(String(stdout).trim(), 10);
      resolve(Number.isFinite(n) ? n : null);
    });
  });
}

/**
 * @param {string} rootDir
 * @param {{ databaseUrl: string, merged?: Record<string, string> }} envBundle
 */
async function inspectDbAsync(rootDir, envBundle) {
  const databaseUrl = envBundle.databaseUrl || '';
  const merged = envBundle.merged || {};
  const mysqlProbe = await probeMysql(databaseUrl);
  const lgMode = String(merged.LANGGRAPH_CHECKPOINTER || 'sqlite').toLowerCase();
  let langgraph = { mode: lgMode, tcpOk: false, psqlOk: false, summary: '' };
  if (lgMode === 'postgres' && merged.LANGGRAPH_POSTGRES_URI) {
    langgraph = await probeLanggraphPostgres(rootDir, merged.LANGGRAPH_POSTGRES_URI, merged);
  } else {
    langgraph = {
      mode: lgMode,
      tcpOk: false,
      psqlOk: false,
      summary: lgMode === 'postgres' ? '未配置 LANGGRAPH_POSTGRES_URI' : `checkpoint=${lgMode}`,
    };
  }

  if (!databaseUrl.startsWith('sqlite')) {
    const kind = /^mysql/i.test(databaseUrl) ? 'mysql' : 'other';
    return {
      version: 2,
      kind,
      business: {
        kind,
        preview: maskDbUrlPreview(databaseUrl),
      },
      mysql: mysqlProbe,
      langgraph,
    };
  }

  const fp = resolveSqlitePath(databaseUrl, rootDir);
  if (!fp) {
    return {
      version: 2,
      kind: 'sqlite',
      business: { kind: 'sqlite', error: '无法解析路径' },
      mysql: mysqlProbe,
      langgraph,
    };
  }
  try {
    const st = fs.statSync(fp);
    const dir = path.dirname(fp);
    const baseName = path.basename(fp);
    const wal = path.join(dir, `${baseName}-wal`);
    const shm = path.join(dir, `${baseName}-shm`);
    const tableCount = await tableCountPromise(fp);
    return {
      version: 2,
      kind: 'sqlite',
      business: {
        kind: 'sqlite',
        path: fp,
        size: st.size,
        sizeText: formatBytes(st.size),
        wal: fs.existsSync(wal),
        shm: fs.existsSync(shm),
        tableCount,
      },
      mysql: mysqlProbe,
      langgraph,
    };
  } catch (e) {
    return {
      version: 2,
      kind: 'sqlite',
      business: { kind: 'sqlite', path: fp, error: e.message },
      mysql: mysqlProbe,
      langgraph,
    };
  }
}

module.exports = { inspectDbAsync, resolveSqlitePath };
