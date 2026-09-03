const net = require('net');
const http = require('http');
const { execFile } = require('child_process');

function portListening(port, timeoutMs = 400) {
  return new Promise((resolve) => {
    const sock = net.createConnection({ port, host: '127.0.0.1' }, () => {
      sock.destroy();
      resolve(true);
    });
    sock.on('error', () => resolve(false));
    sock.setTimeout(timeoutMs, () => {
      sock.destroy();
      resolve(false);
    });
  });
}

function httpOk(url, timeoutMs = 550) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      const ok = res.statusCode >= 200 && res.statusCode < 400;
      res.resume();
      resolve(ok);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

/** 与后端 `/healthz` 契约一致：仅 200 且 JSON `{"status":"ok"}` 视为就绪 */
function httpHealthzStrict(url, timeoutMs = 1200) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        if (res.statusCode !== 200) {
          resolve(false);
          return;
        }
        try {
          const j = JSON.parse(Buffer.concat(chunks).toString('utf8'));
          resolve(Boolean(j && j.status === 'ok'));
        } catch {
          resolve(false);
        }
      });
      res.on('error', () => resolve(false));
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

function ps(cmd) {
  return new Promise((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd],
      { windowsHide: true, maxBuffer: 2 * 1024 * 1024 },
      (err, stdout) => {
        if (err && !stdout) reject(err);
        else resolve(String(stdout || '').trim());
      }
    );
  });
}

async function getPidsOnPort(port) {
  if (process.platform !== 'win32') return [];
  const script = `$p=${port}; (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) -join ','`;
  try {
    const out = await ps(script);
    if (!out) return [];
    return out
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => Number.isFinite(n) && n > 4);
  } catch {
    return [];
  }
}

async function findViteDevPort() {
  for (let p = 5173; p <= 5180; p += 1) {
    if (await httpOk(`http://127.0.0.1:${p}/`, 650)) return p;
  }
  return null;
}

async function firstListenPortInRange(lo, hi) {
  for (let p = lo; p <= hi; p += 1) {
    if (await portListening(p)) return p;
  }
  return null;
}

async function getStatus(apiPort) {
  const apiListen = await portListening(apiPort);
  let apiOk = false;
  const healthUrl = `http://127.0.0.1:${apiPort}/healthz`;
  if (apiListen) apiOk = await httpHealthzStrict(healthUrl, 1200);
  const apiPids = apiListen ? await getPidsOnPort(apiPort) : [];

  const webReadyPort = await findViteDevPort();
  const webListenPort = webReadyPort ?? (await firstListenPortInRange(5173, 5180));
  const webOk = webReadyPort != null;
  const webListen = webListenPort != null;
  const webPids = webListenPort != null ? await getPidsOnPort(webListenPort) : [];

  return {
    apiPort,
    apiListen,
    webListen,
    apiOk,
    webOk,
    apiPids,
    webPids,
    webPort: webListenPort,
  };
}

async function waitUntilHealthy(apiPort, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? 90000;
  const intervalMs = opts.intervalMs ?? 600;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const s = await getStatus(apiPort);
    if (s.apiOk && s.webOk) return { ok: true, status: s };
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  const status = await getStatus(apiPort);
  return { ok: false, status };
}

/**
 * 仅等待 API `/healthz`（避免 Vite 代理早于 Uvicorn worker 就绪而出现 ECONNREFUSED）。
 * 要求连续两次严格校验通过且间隔 settleGapMs，避免 reload 窗口或瞬时误报。
 */
async function waitUntilApiReady(apiPort, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? 120000;
  const intervalMs = opts.intervalMs ?? 400;
  const settleGapMs = opts.settleGapMs ?? 700;
  const onProgress = typeof opts.onProgress === 'function' ? opts.onProgress : null;
  const url = `http://127.0.0.1:${apiPort}/healthz`;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await httpHealthzStrict(url, 2200)) {
      await new Promise((r) => setTimeout(r, settleGapMs));
      if (await httpHealthzStrict(url, 2200)) return { ok: true };
    }
    if (onProgress) onProgress(Date.now() - start);
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return { ok: false };
}

module.exports = {
  getStatus,
  waitUntilHealthy,
  waitUntilApiReady,
  httpOk,
  httpHealthzStrict,
  portListening,
};
