(() => {
  const L = window.launcher;
  if (!L) {
    document.body.innerHTML = '<p style="padding:24px;color:#fff">preload 未加载</p>';
    return;
  }

  const el = (id) => document.getElementById(id);
  const logEl = el('log');
  const summary = el('summary');
  const svcBody = el('svc-body');
  const configHint = el('config-hint');
  const overviewHint = el('overview-hint');
  const rootPathEl = el('root-path');

  let apiPortCached = 8001;
  let logFilter = 'all';

  /** 滚离底部则暂停自动跟随；回到底部恢复。在底部按下鼠标也会暂停，便于框选复制。 */
  const LOG_STICK_THRESHOLD_PX = 56;
  let logUserLocked = false;
  const logScrollHint = el('log-scroll-hint');

  function logDistanceFromBottom() {
    return logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight;
  }

  function syncLogScrollLockFromScrollPosition() {
    logUserLocked = logDistanceFromBottom() > LOG_STICK_THRESHOLD_PX;
  }

  function updateLogScrollHint() {
    if (!logScrollHint) return;
    if (logUserLocked) {
      logScrollHint.textContent = '已暂停：新日志不会自动滚到底。滚回底部恢复。';
      logScrollHint.classList.add('is-locked');
    } else {
      logScrollHint.textContent = '滚离底部或在底部点击可暂停自动滚动，便于复制。';
      logScrollHint.classList.remove('is-locked');
    }
  }

  logEl.addEventListener(
    'scroll',
    () => {
      syncLogScrollLockFromScrollPosition();
      updateLogScrollHint();
    },
    { passive: true },
  );

  logEl.addEventListener('mousedown', () => {
    if (logDistanceFromBottom() <= LOG_STICK_THRESHOLD_PX) {
      logUserLocked = true;
      updateLogScrollHint();
    }
  });

  updateLogScrollHint();

  /**
   * 日志语义色（与 styles.css 中 .log .l-* 对应）：
   * - line / info：日常主日志（浅灰白）
   * - stderr：子进程 stderr 默认流（青灰，非错误）
   * - err / warn：由 refineLogKind 从 stderr 提升，或编排层显式标记
   * - accent：阶段标题；ok：成功；muted：旁白/进度提示
   */
  const logClass = {
    line: 'l-line',
    info: 'l-line',
    stderr: 'l-stderr',
    accent: 'l-accent',
    ok: 'l-ok',
    warn: 'l-warn',
    err: 'l-err',
    muted: 'l-muted',
  };

  /** 将「仅为 stderr 流」与「语义上的警告/错误」区分开，避免满屏红。 */
  function refineLogKind(kind, text) {
    if (kind !== 'stderr') return kind;
    const t = String(text).trim();
    if (!t) return 'stderr';
    // Uvicorn / 多数框架把 INFO 打到 stderr，与错误流区分：按主日志色显示
    if (/^(INFO|DEBUG|TRACE)\b/.test(t)) return 'line';
    const errLike =
      /Traceback|AssertionError|UnhandledPromise|Unhandled\s|rejection|npm ERR!|ERR_PNPM|Failed to compile|Failed to resolve|Exception:|SyntaxError|ReferenceError|TypeError:/i.test(
        t
      ) ||
      /\berror TS\d+/i.test(t) ||
      /\b(ERROR|FATAL)\s*:/i.test(t) ||
      /\bError:\s+\S/.test(t) ||
      /\b(ECONNREFUSED|ENOTFOUND|EADDRINUSE)\b/.test(t) ||
      /\b(exited with code|exit code)\s+[1-9]\d*\b/i.test(t) ||
      /^[\s│├╰─]*[×✗]\s/i.test(t);
    if (errLike) return 'err';
    if (/^WARN(ING)?\b|\bwarning:\s|deprecated in|DeprecationWarning|\(!\)|\b⚠/i.test(t)) return 'warn';
    return 'stderr';
  }

  function applyLogFilter() {
    logEl.querySelectorAll('[data-ch]').forEach((node) => {
      const ch = node.getAttribute('data-ch');
      const show = logFilter === 'all' || ch === logFilter;
      node.classList.toggle('span-hidden', !show);
    });
  }

  function appendLog(payload) {
    const p =
      typeof payload === 'object' && payload && 'text' in payload
        ? payload
        : { text: String(payload), kind: 'info', channel: 'orch' };
    const text = p.text;
    const rawKind = p.kind || 'info';
    const channel = p.channel || 'orch';
    const kind = refineLogKind(rawKind, text);

    const span = document.createElement('span');
    span.setAttribute('data-ch', channel);
    span.setAttribute('data-lk', kind);
    const cls = logClass[kind] || logClass.line;
    span.className = cls;
    span.textContent = text + '\n';
    logEl.appendChild(span);
    applyLogFilter();
    if (!logUserLocked) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  }

  const offLog = L.onLog((payload) => appendLog(payload));

  window.addEventListener('beforeunload', () => {
    offLog();
  });

  function rowState(listen, ready) {
    if (ready) return { label: '就绪', cls: 'dot-ok' };
    if (listen) return { label: '监听中', cls: 'dot-warn' };
    return { label: '未启动', cls: 'dot-bad' };
  }

  function allSystemsGreen(s, dbInfo, infra) {
    if (!s.apiOk || !s.webOk) return false;
    if (dbInfo && dbInfo.version === 2 && dbInfo.mysql && dbInfo.mysql.enabled && !dbInfo.mysql.tcpOk) {
      return false;
    }
    const lgMode = String(dbInfo?.langgraph?.mode || '').toLowerCase();
    if (lgMode === 'postgres' && dbInfo.langgraph) {
      const g = dbInfo.langgraph;
      if (!g.tcpOk || !g.psqlOk) return false;
    }
    const redisNeeded =
      infra?.redis?.urlPreview && !String(infra.redis.urlPreview).startsWith('（未配置');
    if (redisNeeded && infra.redis && !infra.redis.tcpListen) return false;
    return true;
  }

  function renderTable(s, dbInfo, infra) {
    const apiPortStr = s.apiPort != null ? String(s.apiPort) : String(apiPortCached);
    const rows = [
      {
        name: '后端 API',
        port: apiPortStr,
        listen: s.apiListen,
        ready: s.apiOk,
        hint: 'GET /healthz（TA_DEV_API_PORT）',
        pids: s.apiPids,
      },
      {
        name: '前端 Vite',
        port: s.webPort != null ? String(s.webPort) : '5173–5180',
        listen: s.webListen,
        ready: s.webOk,
        hint: '开发服务器',
        pids: s.webPids,
      },
    ];
    if (dbInfo && dbInfo.version === 2) {
      if (dbInfo.mysql && dbInfo.mysql.enabled) {
        const m = dbInfo.mysql;
        rows.push({
          name: 'MySQL（业务库）',
          port: m.port != null ? String(m.port) : '—',
          listen: m.tcpOk,
          ready: m.tcpOk,
          hint: m.summary || 'TCP 探测',
          pids: [],
        });
      }
      const lgMode = String(dbInfo.langgraph?.mode || '').toLowerCase();
      if (lgMode === 'postgres') {
        const g = dbInfo.langgraph;
        const pgInfra = infra?.postgres;
        const ready = !!(g.tcpOk && g.psqlOk);
        let hint = g.summary || 'LANGGRAPH_POSTGRES_URI';
        if (pgInfra?.summary) hint += ` · ${pgInfra.summary}`;
        if (!ready) hint += ' · 可点上方 PostgreSQL 拉起';
        rows.push({
          name: 'PostgreSQL（LangGraph）',
          port: g.port != null ? String(g.port) : pgInfra?.probePort != null ? String(pgInfra.probePort) : '—',
          listen: g.tcpOk,
          ready,
          hint,
          pids: [],
        });
      }
    }
    const rd = infra?.redis;
    if (rd && rd.urlPreview && !String(rd.urlPreview).startsWith('（未配置')) {
      rows.push({
        name: 'Redis',
        port: rd.probePort != null ? String(rd.probePort) : '—',
        listen: rd.tcpListen,
        ready: rd.tcpListen,
        hint: rd.summary || rd.urlPreview,
        pids: [],
      });
    }
    svcBody.innerHTML = rows
      .map((r) => {
        const st = rowState(r.listen, r.ready);
        const pidTxt = r.pids && r.pids.length ? r.pids.join(', ') : '—';
        return `<tr><td><span class="dot ${st.cls}"></span>${r.name}</td><td>${st.label}</td><td>${r.port}</td><td>${pidTxt}</td><td>${r.hint}</td></tr>`;
      })
      .join('');
    if (overviewHint) {
      const n = rows.length;
      const ok = rows.filter((r) => r.ready).length;
      overviewHint.textContent = `${ok}/${n} 项就绪 · 开发服务 · 数据与缓存`;
    }
  }

  function renderSummary(s, dbInfo, infra) {
    summary.classList.remove('is-ok', 'is-warn', 'is-err');
    if (allSystemsGreen(s, dbInfo, infra)) {
      summary.textContent = '当前：环境与前后端均已就绪（全部绿灯），可正常使用。';
      summary.classList.add('is-ok');
      return;
    }
    if (s.apiOk && s.webOk) {
      summary.textContent = '当前：前后端已就绪；部分数据/缓存项未绿灯，请查看下表或点 PostgreSQL / Redis。';
      summary.classList.add('is-warn');
      return;
    }
    if (s.apiOk || s.webOk) {
      summary.textContent = '当前：仅部分开发服务就绪；请等待或查看「日志」。';
      summary.classList.add('is-warn');
      return;
    }
    const dataOk =
      dbInfo &&
      dbInfo.version === 2 &&
      (!dbInfo.mysql?.enabled || dbInfo.mysql.tcpOk) &&
      (String(dbInfo.langgraph?.mode || '').toLowerCase() !== 'postgres' ||
        (dbInfo.langgraph.tcpOk && dbInfo.langgraph.psqlOk)) &&
      (!infra?.redis?.urlPreview ||
        String(infra.redis.urlPreview).startsWith('（未配置') ||
        infra.redis.tcpListen);
    if (dataOk) {
      summary.textContent =
        '当前：数据环境已就绪，开发进程未启动。正在自动启动或请点击左侧「智能一键」。';
      summary.classList.add('is-warn');
      return;
    }
    summary.textContent =
      '当前：尚未全部就绪。智能一键将自动拉起 MySQL 探测、Postgres、Redis 与前后端；也可在上方手动启动 PostgreSQL / Redis。';
    summary.classList.add('is-err');
  }

  async function refreshStatus() {
    try {
      const [s, dbInfo, infra] = await Promise.all([L.getStatus(), L.getDbInfo(), L.getInfraStatus()]);
      if (s.apiPort != null) apiPortCached = s.apiPort;
      renderTable(s, dbInfo, infra);
      renderSummary(s, dbInfo, infra);
    } catch (e) {
      appendLog({ text: `[状态] ${e.message}`, kind: 'err', channel: 'orch' });
    }
  }

  const LS = {
    stop: 'launcher.opt.stop',
    uv: 'launcher.opt.uv',
    build: 'launcher.opt.build',
    clear: 'launcher.opt.clear',
    exit: 'launcher.opt.exit',
  };

  function loadPrefs() {
    el('opt-stop').checked = localStorage.getItem(LS.stop) !== '0';
    el('opt-uv').checked = localStorage.getItem(LS.uv) !== '0';
    el('opt-build').checked = localStorage.getItem(LS.build) !== '0';
    el('opt-clear').checked = localStorage.getItem(LS.clear) !== '0';
    el('opt-exit-stop').checked = localStorage.getItem(LS.exit) === '1';
    L.setExitStopPorts(el('opt-exit-stop').checked);
  }

  function wirePrefs() {
    const sync = () => {
      localStorage.setItem(LS.stop, el('opt-stop').checked ? '1' : '0');
      localStorage.setItem(LS.uv, el('opt-uv').checked ? '1' : '0');
      localStorage.setItem(LS.build, el('opt-build').checked ? '1' : '0');
      localStorage.setItem(LS.clear, el('opt-clear').checked ? '1' : '0');
      localStorage.setItem(LS.exit, el('opt-exit-stop').checked ? '1' : '0');
      L.setExitStopPorts(el('opt-exit-stop').checked);
    };
    ['opt-stop', 'opt-uv', 'opt-build', 'opt-clear', 'opt-exit-stop'].forEach((id) => {
      el(id).addEventListener('change', sync);
    });
  }

  function showView(view) {
    document.querySelectorAll('.nav-item').forEach((b) => {
      const on = b.dataset.view === view;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('.view').forEach((v) => {
      v.classList.toggle('is-visible', v.id === `view-${view}`);
    });
  }

  el('nav').addEventListener('click', (e) => {
    const t = e.target.closest('.nav-item');
    if (!t) return;
    showView(t.dataset.view);
  });

  document.querySelectorAll('[data-log-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      logFilter = btn.getAttribute('data-log-tab') || 'all';
      document.querySelectorAll('[data-log-tab]').forEach((b) => b.classList.toggle('is-active', b === btn));
      applyLogFilter();
    });
  });

  el('btn-smart').addEventListener('click', async () => {
    el('btn-smart').disabled = true;
    try {
      await L.smartRun({
        stopFirst: el('opt-stop').checked,
        uvSync: el('opt-uv').checked,
        build: el('opt-build').checked,
        clearCaches: el('opt-clear').checked,
      });
      await refreshStatus();
    } finally {
      el('btn-smart').disabled = false;
    }
  });

  el('btn-restart').addEventListener('click', async () => {
    el('btn-restart').disabled = true;
    try {
      await L.restart({ claimPorts: el('opt-stop').checked });
      await refreshStatus();
    } finally {
      el('btn-restart').disabled = false;
    }
  });

  el('btn-stop-ports').addEventListener('click', async () => {
    await L.stopPorts();
    await refreshStatus();
  });

  el('btn-stop-services').addEventListener('click', async () => {
    await L.stopServices();
    await refreshStatus();
  });

  el('btn-web').addEventListener('click', async () => {
    const url = await L.webDevUrl();
    await L.openUrl(url);
  });

  el('btn-web-mobile').addEventListener('click', async () => {
    const url = await L.webDevUrl();
    await L.openUrl(url + '/m');
  });

  el('btn-clear').addEventListener('click', () => {
    logEl.textContent = '';
    logUserLocked = false;
    updateLogScrollHint();
  });

  el('btn-deps').addEventListener('click', async () => {
    const rows = await L.checkDeps();
    const txt = rows.map((r) => `  ${r.ok ? '[√]' : '[×]'} ${r.name}: ${r.version}`).join('\n');
    appendLog({ text: `依赖检测：\n${txt}`, kind: 'accent', channel: 'orch' });
    alert(`依赖检测\n\n${rows.map((r) => `${r.ok ? '[√]' : '[×]'} ${r.name}: ${r.version}`).join('\n')}`);
  });

  const btnPg = el('btn-infra-pg');
  const btnRedis = el('btn-infra-redis');
  if (btnPg) {
    btnPg.addEventListener('click', async () => {
      btnPg.disabled = true;
      try {
        await L.restartPostgres();
        await refreshStatus();
      } catch (e) {
        appendLog({ text: `[PostgreSQL] ${e.message}`, kind: 'err', channel: 'orch' });
      } finally {
        btnPg.disabled = false;
      }
    });
  }
  if (btnRedis) {
    btnRedis.addEventListener('click', async () => {
      btnRedis.disabled = true;
      try {
        await L.restartRedis();
        await refreshStatus();
      } catch (e) {
        appendLog({ text: `[Redis] ${e.message}`, kind: 'err', channel: 'orch' });
      } finally {
        btnRedis.disabled = false;
      }
    });
  }

  (async () => {
    const { root } = await L.getPaths();
    const cfg = await L.getConfig();
    apiPortCached = cfg.apiPort ?? 8001;
    rootPathEl.textContent = `项目目录：${root}`;
    const lg =
      cfg.langgraphMode || cfg.langgraphUriPreview
        ? `；LangGraph: ${cfg.langgraphMode || '—'} ${cfg.langgraphUriPreview ? `URI ${cfg.langgraphUriPreview}` : ''}`
        : '';
    configHint.textContent = `当前解析 API 端口：${cfg.apiPort}（可在仓库根 .env 设置 TA_DEV_API_PORT）；业务库 ${cfg.databaseUrlPreview || '—'}${lg}；本机路径 TA_POSTGRES_HOME=${cfg.taPostgresHome || '（未设）'}；TA_REDIS_HOME=${cfg.taRedisHome || '（未设）'}`;
    appendLog({ text: `项目目录：${root}`, kind: 'muted', channel: 'orch' });
    appendLog({
      text: cfg.skipAutoBootstrap
        ? `已跳过自动冷启动（TA_DEV_LAUNCHER_SKIP_AUTO=1）；需要时请点「智能一键」。`
        : `即将自动拉起环境（MySQL / Postgres / Redis）并启动前后端，等待全部绿灯…`,
      kind: 'accent',
      channel: 'orch',
    });
    loadPrefs();
    wirePrefs();
    await refreshStatus();
    if (!cfg.skipAutoBootstrap) {
      el('btn-smart').disabled = true;
      try {
        await L.smartRun({
          stopFirst: el('opt-stop').checked,
          uvSync: el('opt-uv').checked,
          build: el('opt-build').checked,
          clearCaches: el('opt-clear').checked,
        });
        await refreshStatus();
      } catch (e) {
        appendLog({ text: `[自动启动] ${e.message}`, kind: 'err', channel: 'orch' });
      } finally {
        el('btn-smart').disabled = false;
      }
    }
    setInterval(refreshStatus, 2200);
  })();
})();
