const { execFile, execFileSync } = require('child_process');

/**
 * Windows：释放开发常用端口（与 Vite / dev-api 约定一致）。
 * 脚本内吞掉 Get-NetTCPConnection / Stop-Process 的可预期错误，并固定 exit 0，
 * 避免 Node 将非零退出码当作「整段命令失败」而误报。
 */
const PS_CLAIM_PORTS =
  "$ErrorActionPreference='SilentlyContinue'; " +
  'try { ' +
  '$ports=@(8000,8001)+(5173..5180); ' +
  'foreach($p in $ports){ ' +
  '$conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; ' +
  'if ($null -eq $conns) { continue }; ' +
  'foreach($c in @($conns)){ ' +
  '$id=[int]$c.OwningProcess; ' +
  'if($id -gt 4){ Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } ' +
  '} } } catch {} ' +
  'exit 0';

/** Windows：释放开发常用端口（与 Vite / dev-api 约定一致） */
function claimDevPortsWin() {
  if (process.platform !== 'win32') return Promise.resolve();
  return new Promise((resolve) => {
    execFile(
      'powershell.exe',
      ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', PS_CLAIM_PORTS],
      { windowsHide: true, maxBuffer: 2 * 1024 * 1024 },
      () => resolve()
    );
  });
}

function claimDevPortsWinSync() {
  if (process.platform !== 'win32') return;
  try {
    execFileSync('powershell.exe', ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', PS_CLAIM_PORTS], {
      windowsHide: true,
      stdio: 'ignore',
    });
  } catch (_) {}
}

module.exports = { claimDevPortsWin, claimDevPortsWinSync };
