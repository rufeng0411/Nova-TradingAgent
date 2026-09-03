const { spawn } = require('child_process');
const path = require('path');
const { attachDecodedLineStream } = require('./console-decode.cjs');

/**
 * 分别拉起 API（node scripts/dev-api.mjs）与前端（npm run dev:web）。
 */
function createSupervisor({ root, onLine }) {
  let apiChild = null;
  let webChild = null;

  /** onLine(channel, line, isStderr) */
  function pipe(child, channel) {
    attachDecodedLineStream(child.stdout, (line) => onLine(channel, line, false));
    attachDecodedLineStream(child.stderr, (line) => onLine(channel, line, true));
  }

  function killTree(child) {
    if (!child || child.killed) return;
    if (process.platform === 'win32') {
      try {
        spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      } catch (_) {}
    } else {
      try {
        child.kill('SIGTERM');
      } catch (_) {}
    }
  }

  function startApi(extraEnv) {
    if (apiChild && !apiChild.killed) return;
    const script = path.join(root, 'scripts', 'dev-api.mjs');
    apiChild = spawn(process.execPath, [script], {
      cwd: root,
      shell: false,
      windowsHide: true,
      env: { ...process.env, ...extraEnv, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
    });
    pipe(apiChild, 'api');
    apiChild.on('close', () => {
      apiChild = null;
    });
    apiChild.on('error', () => {
      apiChild = null;
    });
  }

  function startWeb() {
    if (webChild && !webChild.killed) return;
    const env = {
      ...process.env,
      FORCE_COLOR: '0',
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
    };
    if (process.platform === 'win32') {
      webChild = spawn('cmd.exe', ['/d', '/s', '/c', 'chcp 65001 >nul && npm run dev:web'], {
        cwd: root,
        windowsHide: true,
        env,
      });
    } else {
      const npm = 'npm';
      webChild = spawn(npm, ['run', 'dev:web'], {
        cwd: root,
        shell: true,
        windowsHide: true,
        env,
      });
    }
    pipe(webChild, 'web');
    webChild.on('close', () => {
      webChild = null;
    });
    webChild.on('error', () => {
      webChild = null;
    });
  }

  function stopAll() {
    killTree(webChild);
    webChild = null;
    killTree(apiChild);
    apiChild = null;
  }

  return {
    startApi,
    startWeb,
    stopAll,
    get apiPid() {
      return apiChild?.pid;
    },
    get webPid() {
      return webChild?.pid;
    },
  };
}

module.exports = { createSupervisor };
