const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('launcher', {
  getStatus: () => ipcRenderer.invoke('status:get'),
  getConfig: () => ipcRenderer.invoke('config:get'),
  getDbInfo: () => ipcRenderer.invoke('db:info'),
  webDevUrl: () => ipcRenderer.invoke('web:dev-url'),
  stopPorts: () => ipcRenderer.invoke('dev:stop-ports'),
  stopServices: () => ipcRenderer.invoke('dev:stop-services'),
  smartRun: (opts) => ipcRenderer.invoke('dev:smart-run', opts),
  restart: (opts) => ipcRenderer.invoke('dev:restart', opts),
  openUrl: (url) => ipcRenderer.invoke('shell:open-url', url),
  checkDeps: () => ipcRenderer.invoke('deps:check'),
  getPaths: () => ipcRenderer.invoke('paths:get'),
  setExitStopPorts: (v) => ipcRenderer.invoke('app:set-exit-stop-ports', v),
  getInfraStatus: () => ipcRenderer.invoke('infra:status'),
  restartPostgres: () => ipcRenderer.invoke('infra:restart-postgres'),
  restartRedis: () => ipcRenderer.invoke('infra:restart-redis'),
  onLog: (fn) => {
    const ch = (_e, payload) => fn(payload);
    ipcRenderer.on('log:line', ch);
    return () => ipcRenderer.removeListener('log:line', ch);
  },
});
