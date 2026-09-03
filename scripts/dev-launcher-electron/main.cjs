const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, execFile, execFileSync } = require('child_process');

const { attachDecodedLineStream } = require('./lib/console-decode.cjs');
const { loadEnv, envForApiChild } = require('./lib/env-resolver.cjs');
const { claimDevPortsWin, claimDevPortsWinSync } = require('./lib/port-claim.cjs');
const { createSupervisor } = require('./lib/process-supervisor.cjs');
const { getStatus, waitUntilHealthy, waitUntilApiReady } = require('./lib/health-status.cjs');
const { inspectDbAsync } = require('./lib/db-inspector.cjs');
const { clearProjectCaches } = require('./lib/project-cache-clear.cjs');
const {
  ensureLanggraphPostgresAsync,
  preflightMysqlTcp,
  maskDbUrlPreview,
} = require('./lib/datastore-probe.cjs');
const {
  getInfraServicesStatus,
  restartPostgres,
  restartRedis,
  ensureRedisAsync,
} = require('./lib/infra-services.cjs');

const ROOT = path.resolve(__dirname, '..', '..');
const LOG_DIR = path.join(ROOT, 'logs');
const DEV_LOG = path.join(LOG_DIR, 'dev-combined.log');

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  console.error(
    '[Nova-TradingAgent dev launcher] 已有开发控制台在运行（单实例锁），本进程退出。请在任务栏或 Alt+Tab 查找已打开的「Nova-TradingAgent 开发控制台」窗口。'
  );
  app.quit();
  process.exit(0);
}

console.log(
  '[Nova-TradingAgent dev launcher] Electron 主进程已启动，即将打开窗口。窗口出现后此处通常不再输出日志，属正常现象；结束请关闭窗口或在此终端按 Ctrl+C。'
);

/** @type {import('electron').BrowserWindow | null} */
let mainWindow = null;

/** @type {ReturnType<createSupervisor> | null} */
let supervisor = null;

function ensureLogDir() {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
  } catch (_) {}
}

function appendDevLog(line) {
  ensureLogDir();
  try {
    fs.appendFileSync(DEV_LOG, line + '\n', 'utf8');
  } catch (_) {}
}

function emitLogChunk(win, payload) {
  const w =
    win && !win.isDestroyed()
      ? win
      : mainWindow && !mainWindow.isDestroyed()
        ? mainWindow
        : null;
  if (!w) return;
  w.webContents.send('log:line', payload);
}

function emitOrch(text, kind = 'accent') {
  emitLogChunk(null, { text, channel: 'orch', kind });
  appendDevLog(`[orch] ${text}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 与前端概览表「绿灯」判定一致 */
function allSystemsGreen(status, dbInfo, infra, merged) {
  if (!status.apiOk || !status.webOk) return false;
  if (dbInfo && dbInfo.version === 2 && dbInfo.mysql && dbInfo.mysql.enabled && !dbInfo.mysql.tcpOk) {
    return false;
  }
  const lgMode = String(merged.LANGGRAPH_CHECKPOINTER || 'sqlite').toLowerCase();
  if (lgMode === 'postgres' && dbInfo && dbInfo.langgraph) {
    const g = dbInfo.langgraph;
    if (!g.tcpOk || !g.psqlOk) return false;
  }
  const redisUrl = String(merged.REDIS_URL || '').trim();
  if (redisUrl && infra && infra.redis && !infra.redis.tcpListen) return false;
  return true;
}

async function ensureDevInfraAsync(win, envBundle) {
  const emitData = (msg, kind) =>
    emitLogChunk(win, { text: msg, channel: 'orch', kind: kind || 'muted' });
  emitOrch('—— 环境预检：MySQL · Postgres · Redis ——', 'accent');
  await preflightMysqlTcp(envBundle.databaseUrl, emitData);
  await ensureLanggraphPostgresAsync(ROOT, envBundle.merged, emitData);
  await ensureRedisAsync(envBundle.merged, emitData);
}

async function waitUntilAllGreen(apiPort, win, { timeoutMs = 120000, intervalMs = 2000 } = {}) {
  const envBundle = loadEnv(ROOT);
  const merged = envBundle.merged || {};
  const start = Date.now();
  let lastEmit = 0;
  while (Date.now() - start < timeoutMs) {
    const [status, dbInfo, infra] = await Promise.all([
      getStatus(apiPort),
      inspectDbAsync(ROOT, envBundle),
      getInfraServicesStatus(ROOT, merged),
    ]);
    if (allSystemsGreen(status, dbInfo, infra, merged)) {
      emitOrch('全部就绪：开发服务与依赖环境均为绿灯。', 'ok');
      return { ok: true, status, dbInfo, infra };
    }
    const elapsed = Date.now() - start;
    if (elapsed - lastEmit >= 12000) {
      lastEmit = elapsed;
      const parts = [];
      if (!status.apiOk) parts.push('API');
      if (!status.webOk) parts.push('前端');
      if (dbInfo?.mysql?.enabled && !dbInfo.mysql.tcpOk) parts.push('MySQL');
      if (
        String(merged.LANGGRAPH_CHECKPOINTER || '').toLowerCase() === 'postgres' &&
        dbInfo?.langgraph &&
        (!dbInfo.langgraph.tcpOk || !dbInfo.langgraph.psqlOk)
      ) {
        parts.push('Postgres');
      }
      if (merged.REDIS_URL && infra?.redis && !infra.redis.tcpListen) parts.push('Redis');
      emitOrch(
        `等待全部绿灯（约 ${Math.round(elapsed / 1000)}s）… 未就绪：${parts.length ? parts.join('、') : '检测中'}`,
        'muted'
      );
    }
    await sleep(intervalMs);
  }
  emitOrch('等待全部绿灯超时：请查看概览表与日志，必要时手动点 PostgreSQL / Redis。', 'warn');
  return { ok: false };
}

function getSupervisor() {
  if (!supervisor) {
    supervisor = createSupervisor({
      root: ROOT,
      onLine: (channel, line, isStderr) => {
        emitLogChunk(null, {
          text: line,
          channel,
          // stderr 常承载进度/INFO，不等价于错误；具体红/琥珀由渲染层语义归类
          kind: isStderr ? 'stderr' : 'line',
        });
        appendDevLog(`[${channel}] ${line}`);
      },
    });
  }
  return supervisor;
}

function runBlocking(cmd, args, cwd, win, title) {
  return new Promise((resolve) => {
    emitOrch(`----- ${title} -----`, 'accent');
    const child = spawn(cmd, args, {
      cwd,
      shell: process.platform === 'win32',
      windowsHide: true,
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    });
    attachDecodedLineStream(child.stdout, (line) =>
      emitLogChunk(win, { text: line, channel: 'orch', kind: 'line' })
    );
    attachDecodedLineStream(child.stderr, (line) =>
      emitLogChunk(win, { text: line, channel: 'orch', kind: 'stderr' })
    );
    child.on('close', (code) => {
      emitOrch(`----- 结束 (exit ${code}) -----`, 'accent');
      appendDevLog(`[${title}] exit=${code}`);
      resolve(code ?? 0);
    });
    child.on('error', (e) => {
      emitLogChunk(win, { text: `[错误] ${e.message}`, channel: 'orch', kind: 'err' });
      resolve(1);
    });
  });
}

async function ensureRootNodeModules(win) {
  const nm = path.join(ROOT, 'node_modules');
  if (fs.existsSync(nm)) return true;
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const code = await runBlocking(npmCmd, ['install'], ROOT, win, 'npm install（根目录）');
  return code === 0;
}

async function ensureFrontendNodeModules(win) {
  const nm = path.join(ROOT, 'frontend', 'node_modules');
  if (fs.existsSync(nm)) return true;
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const code = await runBlocking(npmCmd, ['--prefix', 'frontend', 'install'], ROOT, win, 'npm install（frontend）');
  return code === 0;
}

function scheduleHealthWait(apiPort) {
  setImmediate(async () => {
    emitOrch('等待前后端就绪（最多约 90 秒）…', 'muted');
    const r = await waitUntilHealthy(apiPort, { timeoutMs: 90000, intervalMs: 700 });
    if (r.ok) emitOrch('健康检查：API 与前端均已就绪。', 'ok');
    else emitOrch('健康检查：超时或未全部就绪，请查看上方日志与表格状态。', 'warn');
  });
}

/** 先起 API，待 /healthz 通过再起 Vite，避免代理抢先连 8001 被拒绝 */
async function startApiThenWeb(win, apiPort, childEnv) {
  getSupervisor().startApi(childEnv);
  emitOrch('等待 API /healthz 就绪后再启动前端（避免 Vite 首次代理 ECONNREFUSED）…', 'muted');
  let lastProgressEmit = 0;
  const apiReady = await waitUntilApiReady(apiPort, {
    onProgress: (elapsedMs) => {
      if (elapsedMs - lastProgressEmit >= 10000) {
        lastProgressEmit = elapsedMs;
        emitOrch(`仍在等待 API /healthz（约 ${Math.round(elapsedMs / 1000)}s）；请查看 API 通道是否停在「init_db」或「LangGraph」等步骤。`, 'muted');
      }
    },
  });
  if (!apiReady.ok) {
    emitOrch('[警告] API 在限定时间内未通过 /healthz，仍将启动前端；可稍后刷新页面。', 'warn');
  } else {
    emitOrch('API 已就绪，启动前端开发服务器…', 'ok');
  }
  getSupervisor().startWeb();
  scheduleHealthWait(apiPort);
}

async function runSmartRun(evt, opts) {
  const win = BrowserWindow.fromWebContents(evt.sender);
  const raw = opts && typeof opts === 'object' ? opts : {};
  /** 未传字段时默认全开；仅显式 `false` 关闭 */
  const pick = (key) => (Object.prototype.hasOwnProperty.call(raw, key) ? !!raw[key] : true);
  const o = {
    stopFirst: pick('stopFirst'),
    uvSync: pick('uvSync'),
    build: pick('build'),
    clearCaches: pick('clearCaches'),
  };
  const envBundle = loadEnv(ROOT);

  try {
    if (o.stopFirst) {
      emitOrch('释放端口并停止本启动器拉起的进程…', 'warn');
      try {
        await claimDevPortsWin();
      } catch (e) {
        emitLogChunk(win, { text: `[端口] ${e.message}`, channel: 'orch', kind: 'err' });
      }
      getSupervisor().stopAll();
      await new Promise((r) => setTimeout(r, 450));
    }

    if (o.clearCaches) {
      clearProjectCaches(ROOT, (text, kind) => {
        if (kind === 'err') emitLogChunk(win, { text, channel: 'orch', kind: 'err' });
        else emitOrch(text, kind);
      });
    }

    if (o.uvSync) {
      const uvSyncArgs =
        process.platform === 'win32' ? ['sync', '--no-managed-python'] : ['sync'];
      const codeUv = await runBlocking('uv', uvSyncArgs, ROOT, win, 'uv sync');
      if (codeUv !== 0) emitOrch('[警告] uv sync 非零退出，仍继续。', 'warn');
    }

    if (o.build) {
      const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
      const codeB = await runBlocking(npmCmd, ['--prefix', 'frontend', 'run', 'build'], ROOT, win, 'npm run build（前端）');
      if (codeB !== 0) emitOrch('[警告] 前端 build 失败，仍将尝试启动开发服务。', 'warn');
    }

    if (!(await ensureRootNodeModules(win))) {
      emitOrch('[错误] 根目录 npm install 失败', 'err');
      return getStatus(envBundle.apiPort);
    }
    if (!(await ensureFrontendNodeModules(win))) {
      emitOrch('[错误] frontend npm install 失败', 'err');
      return getStatus(envBundle.apiPort);
    }

    await ensureDevInfraAsync(win, envBundle);

    const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
    ensureLogDir();
    try {
      fs.appendFileSync(DEV_LOG, `\n=== ${ts} 智能一键：启动 API + 前端 ===\n`, 'utf8');
    } catch (_) {}

    emitOrch(`=== ${ts} 启动 node scripts/dev-api.mjs（端口 ${envBundle.apiPort}）与 npm run dev:web ===`, 'ok');

    const childEnv = envForApiChild(process.env, envBundle.apiPort);
    await startApiThenWeb(win, envBundle.apiPort, childEnv);
    await waitUntilAllGreen(envBundle.apiPort, win);
  } catch (err) {
    emitLogChunk(win, { text: `[错误] ${err.message}`, channel: 'orch', kind: 'err' });
  }

  return getStatus(loadEnv(ROOT).apiPort);
}

async function runRestart(evt, opts) {
  const win = BrowserWindow.fromWebContents(evt.sender);
  const o = opts || {};
  const envBundle = loadEnv(ROOT);

  emitOrch('—— 重启开发服务（不跑 npm install / uv sync，适合改代码后快速验证）——', 'accent');

  try {
    getSupervisor().stopAll();
    await new Promise((r) => setTimeout(r, 450));

    await ensureDevInfraAsync(win, envBundle);

    if (o.claimPorts) {
      emitOrch('释放端口 8000 / 8001 / 5173–5180 …', 'warn');
      try {
        await claimDevPortsWin();
      } catch (e) {
        emitLogChunk(win, { text: `[端口] ${e.message}`, channel: 'orch', kind: 'err' });
      }
      await new Promise((r) => setTimeout(r, 350));
    }

    const childEnv = envForApiChild(process.env, envBundle.apiPort);
    await startApiThenWeb(win, envBundle.apiPort, childEnv);
    await waitUntilAllGreen(envBundle.apiPort, win);
  } catch (err) {
    emitLogChunk(win, { text: `[错误] ${err.message}`, channel: 'orch', kind: 'err' });
  }

  return getStatus(envBundle.apiPort);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1040,
    height: 840,
    minWidth: 860,
    minHeight: 648,
    show: false,
    backgroundColor: '#121214',
    title: 'Nova-TradingAgent 开发控制台',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
  });

  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    const msg = `[renderer did-fail-load] code=${errorCode} desc=${errorDescription} url=${validatedURL}`;
    console.error('[Nova-TradingAgent dev launcher]', msg);
    appendDevLog(msg);
  });

  /** 少数环境下 ready-to-show 不触发，窗口会一直隐藏，终端看起来像「卡住」 */
  const showFallbackTimer = setTimeout(() => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (!mainWindow.isVisible()) {
      console.warn(
        '[Nova-TradingAgent dev launcher] 窗口在约 4.5s 内仍未显示，已强制 show()。若白屏或花屏，可尝试设置环境变量 ELECTRON_DISABLE_GPU=1 后重新 npm start。'
      );
      mainWindow.show();
    }
  }, 4500);

  mainWindow.on('closed', () => {
    clearTimeout(showFallbackTimer);
    mainWindow = null;
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());

ipcMain.handle('paths:get', () => ({ root: ROOT }));

ipcMain.handle('config:get', () => {
  const e = loadEnv(ROOT);
  const m = e.merged || {};
  const lgUri = m.LANGGRAPH_POSTGRES_URI || '';
  return {
    apiPort: e.apiPort,
    databaseUrlPreview: maskDbUrlPreview(e.databaseUrl).slice(0, 96),
    skipAutoBootstrap: process.env.TA_DEV_LAUNCHER_SKIP_AUTO === '1',
    langgraphMode: m.LANGGRAPH_CHECKPOINTER || '',
    langgraphUriPreview: lgUri ? maskDbUrlPreview(lgUri).slice(0, 96) : '',
    taPostgresHome: (m.TA_POSTGRES_HOME || '').trim(),
    taPostgresData: (m.TA_POSTGRES_DATA || '').trim(),
    taRedisHome: (m.TA_REDIS_HOME || '').trim(),
    taRedisServerPath: (m.TA_REDIS_SERVER_PATH || '').trim(),
  };
});

ipcMain.handle('status:get', async () => {
  const { apiPort } = loadEnv(ROOT);
  return getStatus(apiPort);
});

ipcMain.handle('db:info', async () => {
  const e = loadEnv(ROOT);
  return inspectDbAsync(ROOT, e);
});

ipcMain.handle('infra:status', async () => {
  const e = loadEnv(ROOT);
  return getInfraServicesStatus(ROOT, e.merged || {});
});

ipcMain.handle('infra:restart-postgres', async (ev) => {
  const win = BrowserWindow.fromWebContents(ev.sender);
  const e = loadEnv(ROOT);
  const emit = (msg, kind) => emitLogChunk(win, { text: msg, channel: 'orch', kind: kind || 'line' });
  return restartPostgres(ROOT, e.merged || {}, emit);
});

ipcMain.handle('infra:restart-redis', async (ev) => {
  const win = BrowserWindow.fromWebContents(ev.sender);
  const e = loadEnv(ROOT);
  const emit = (msg, kind) => emitLogChunk(win, { text: msg, channel: 'orch', kind: kind || 'line' });
  return restartRedis(e.merged || {}, emit);
});

ipcMain.handle('web:dev-url', async () => {
  const { webPort } = await getStatus(loadEnv(ROOT).apiPort);
  const p = webPort ?? 5173;
  return `http://127.0.0.1:${p}/`;
});

ipcMain.handle('shell:open-url', async (_e, url) => {
  await shell.openExternal(url);
  return true;
});

ipcMain.handle('deps:check', async () => {
  const tryVer = (cmd, args) =>
    new Promise((res) => {
      execFile(cmd, args, { windowsHide: true }, (err, stdout) => {
        res(err ? null : String(stdout || '').trim());
      });
    });
  const npmExe = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const vNode = await tryVer('node', ['--version']);
  const vNpm = await tryVer(npmExe, ['--version']);
  const vUv = await tryVer('uv', ['--version']);
  return [
    { name: 'node', version: vNode || '未找到', ok: !!vNode },
    { name: 'npm', version: vNpm || '未找到', ok: !!vNpm },
    { name: 'uv', version: vUv || '未找到', ok: !!vUv },
  ];
});

ipcMain.handle('dev:stop-ports', async (e) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  emitOrch('手动：释放端口…', 'warn');
  try {
    await claimDevPortsWin();
  } catch (err) {
    emitLogChunk(win, { text: String(err.message), channel: 'orch', kind: 'err' });
  }
  getSupervisor().stopAll();
  return getStatus(loadEnv(ROOT).apiPort);
});

ipcMain.handle('dev:stop-services', () => {
  emitOrch('已停止本启动器拉起的 API 与前端进程。', 'muted');
  getSupervisor().stopAll();
  return getStatus(loadEnv(ROOT).apiPort);
});

ipcMain.handle('dev:smart-run', (e, opts) => runSmartRun(e, opts));

ipcMain.handle('dev:restart', (e, opts) => runRestart(e, opts));

ipcMain.handle('app:set-exit-stop-ports', (_e, v) => {
  global.__launcherExitStopPorts = !!v;
  return true;
});

app.on('before-quit', () => {
  try {
    getSupervisor().stopAll();
    if (global.__launcherExitStopPorts && process.platform === 'win32') {
      claimDevPortsWinSync();
    }
  } catch (_) {}
});
