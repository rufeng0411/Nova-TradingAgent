const fs = require('fs');
const path = require('path');

/** 直接删除的相对路径（存在则删，不进入 node_modules 遍历） */
const DIRECT_CACHE_DIRS = [
  ['frontend', 'node_modules', '.vite'],
  ['frontend', '.vite'],
  ['frontend', 'dist'],
  ['.pytest_cache'],
  ['.ruff_cache'],
  ['.mypy_cache'],
];

/** 在这些根目录下递归删除名为 __pycache__ 的目录（跳过 node_modules / .git） */
const PY_CACHE_WALK_ROOTS = ['api', 'tradingagents', 'scripts'];

/**
 * @param {string} root 仓库根
 * @param {(text: string, kind: 'accent'|'muted'|'warn'|'err'|'ok') => void} log
 */
function clearProjectCaches(root, log) {
  log('----- 清空项目缓存（Vite / 测试工具 / Python __pycache__ 等） -----', 'accent');

  for (const parts of DIRECT_CACHE_DIRS) {
    const target = path.join(root, ...parts);
    if (!fs.existsSync(target)) continue;
    try {
      fs.rmSync(target, { recursive: true, force: true });
      log(`已删除: ${parts.join('/')}`, 'muted');
    } catch (e) {
      log(`[缓存] 删除失败 ${parts.join('/')}: ${e.message}`, 'err');
    }
  }

  for (const sub of PY_CACHE_WALK_ROOTS) {
    const base = path.join(root, sub);
    if (fs.existsSync(base)) walkRemovePyCacheDirs(base, root, log, 0);
  }

  log('----- 缓存清理结束 -----', 'accent');
}

function walkRemovePyCacheDirs(dir, root, log, depth) {
  if (depth > 28) return;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const ent of entries) {
    if (ent.name === 'node_modules' || ent.name === '.git') continue;
    const full = path.join(dir, ent.name);
    if (!ent.isDirectory()) continue;
    if (ent.name === '__pycache__') {
      try {
        fs.rmSync(full, { recursive: true, force: true });
        log(`已删除: ${path.relative(root, full)}`, 'muted');
      } catch (e) {
        log(`[缓存] 无法删除 ${full}: ${e.message}`, 'err');
      }
    } else {
      walkRemovePyCacheDirs(full, root, log, depth + 1);
    }
  }
}

module.exports = { clearProjectCaches };
