/**
 * Windows 下 cmd/npm 常输出 GBK；Python 在 PYTHONUTF8=1 下多为 UTF-8。
 * 按行缓冲，UTF-8 若含替换字符则对该行尝试 GBK 解码。
 */
let iconvLite = null;
try {
  iconvLite = require('iconv-lite');
} catch (_) {}

function decodeLineBuffer(buf) {
  const utf8 = buf.toString('utf8');
  if (!utf8.includes('\uFFFD')) {
    return utf8.replace(/\r$/, '');
  }
  if (iconvLite) {
    try {
      return iconvLite.decode(buf, 'gbk').replace(/\r$/, '');
    } catch (_) {}
  }
  return utf8.replace(/\r$/, '');
}

/**
 * 单路流按行输出（避免 stdout/stderr 混同一缓冲）
 * @param {import('stream').Readable | null | undefined} stream
 * @param {(line: string) => void} onLine
 * @param {() => void} [onEnd]
 */
function attachDecodedLineStream(stream, onLine, onEnd) {
  if (!stream) {
    onEnd?.();
    return;
  }
  let carry = Buffer.alloc(0);
  stream.on('data', (chunk) => {
    carry = Buffer.concat([carry, chunk]);
    let idx;
    while ((idx = carry.indexOf(0x0a)) >= 0) {
      const lineBuf = carry.slice(0, idx);
      carry = carry.slice(idx + 1);
      const text = decodeLineBuffer(lineBuf);
      if (text.length) onLine(text);
    }
  });
  stream.on('end', () => {
    if (carry.length) {
      const text = decodeLineBuffer(carry);
      if (text.length) onLine(text);
      carry = Buffer.alloc(0);
    }
    onEnd?.();
  });
}

module.exports = { decodeLineBuffer, attachDecodedLineStream };
