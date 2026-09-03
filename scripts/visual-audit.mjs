/**
 * 逐页打开前端路由，全页截图；可选录屏（需 `npx playwright install ffmpeg`）。
 * 使用系统 Edge，无需下载 Chromium。
 * 运行前请先启动: cd frontend; npm run dev
 * 用法: node scripts/visual-audit.mjs [baseUrl] [输出子目录]
 * 录屏: set RECORD_VIDEO=1 （Windows: $env:RECORD_VIDEO=1）
 */
import { chromium } from 'playwright'
import { mkdir, writeFile, readdir } from 'fs/promises'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')
const useVideo = process.env.RECORD_VIDEO === '1' || process.env.RECORD_VIDEO === 'true'

const baseUrl = process.argv[2] || 'http://127.0.0.1:5174'
/** 可选第三参数：输出子目录（相对项目根），例如 verification-screenshots/prod */
const outArg = process.argv[3]
const OUT = outArg ? join(ROOT, outArg.replace(/^[/\\]+/, '')) : join(ROOT, 'verification-screenshots')
let VIDEO_DIR = join(OUT, 'videos')

const routes = [
  { path: '/login', name: '01-login' },
  { path: '/sponsor', name: '02-sponsor' },
  { path: '/thanks', name: '03-thanks' },
  { path: '/', name: '04-root' },
  { path: '/analysis', name: '05-analysis' },
  { path: '/reports', name: '06-reports' },
  { path: '/portfolio', name: '07-portfolio' },
  { path: '/tracking-board', name: '08-tracking-board' },
  { path: '/feedback', name: '09-feedback' },
  { path: '/settings', name: '10-settings' },
]

async function main() {
  VIDEO_DIR = join(OUT, 'videos')
  await mkdir(OUT, { recursive: true })
  if (useVideo) await mkdir(VIDEO_DIR, { recursive: true })

  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
  })

  const results = []
  const startedAt = new Date().toISOString()

  const contextOptions = {
    viewport: { width: 1280, height: 720 },
    locale: 'zh-CN',
  }
  if (useVideo) {
    await mkdir(VIDEO_DIR, { recursive: true })
    contextOptions.recordVideo = { dir: VIDEO_DIR, size: { width: 1280, height: 720 } }
  }

  const ctx = await browser.newContext(contextOptions)
  const vpage = await ctx.newPage()
  vpage.setDefaultTimeout(45000)

  for (const { path: p, name } of routes) {
    const url = `${baseUrl.replace(/\/$/, '')}${p}`
    const t0 = Date.now()
    let finalUrl = ''
    let title = ''
    let error = null
    try {
      const resp = await vpage.goto(url, { waitUntil: 'domcontentloaded' })
      await new Promise((r) => setTimeout(r, 800))
      finalUrl = vpage.url()
      title = await vpage.title()
      await vpage.screenshot({
        path: join(OUT, `${name}.png`),
        fullPage: true,
      })
      results.push({
        name,
        requestUrl: url,
        finalUrl,
        title,
        httpStatus: resp?.status() ?? null,
        ms: Date.now() - t0,
        screenshot: `${name}.png`,
        ok: true,
      })
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      results.push({
        name,
        requestUrl: url,
        finalUrl: vpage.url(),
        title: '',
        httpStatus: null,
        ms: Date.now() - t0,
        error,
        ok: false,
      })
    }
  }

  await vpage.close()
  await ctx.close()

  let videoFiles = []
  if (useVideo) {
    try {
      videoFiles = (await readdir(VIDEO_DIR)).filter((f) => f.endsWith('.webm'))
    } catch {
      videoFiles = []
    }
  }

  const report = {
    baseUrl,
    timestamp: startedAt,
    recordVideo: useVideo,
    videoFiles,
    results,
  }

  await writeFile(join(OUT, 'audit-report.json'), JSON.stringify(report, null, 2), 'utf8')

  const summaryPath = join(OUT, 'SUMMARY.md')
  const lines = [
    `# 前端路由自动化核对`,
    ``,
    `- 基准 URL: \`${baseUrl}\``,
    `- 时间: ${report.timestamp}`,
    `- 浏览器: Microsoft Edge (channel)`,
    `- 录屏: ${useVideo ? `已启用（见 videos/*.webm）` : '未启用（设置 RECORD_VIDEO=1 且需 npx playwright install ffmpeg）'}`,
    ``,
    `| # | 路由 | 最终 URL | 标题 | HTTP | 截图 |`,
    `|---|------|----------|------|------|------|`,
  ]
  for (const r of results) {
    lines.push(
      `| ${r.name} | ${r.requestUrl?.replace(baseUrl, '') || ''} | ${r.finalUrl || '-'} | ${(r.title || '').slice(0, 40)} | ${r.httpStatus ?? '-'} | ${r.screenshot || r.error || 'FAIL'} |`,
    )
  }
  lines.push(``, `说明：未登录时受保护路由应重定向到 /login。`)
  await writeFile(summaryPath, lines.join('\n'), 'utf8')

  await browser.close()
  console.log('Done. Output:', OUT)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
