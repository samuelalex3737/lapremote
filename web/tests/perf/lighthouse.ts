/**
 * Lighthouse audit of the built Remote app, as served by a running agent.
 *
 *   npm run lighthouse -- http://127.0.0.1:7777/
 *
 * Playwright's Chromium is launched with a debugging port and Lighthouse attaches to it
 * (mobile emulation, the Lighthouse default). Prints category scores and core metrics.
 */
import { writeFileSync } from 'node:fs'
import { chromium } from '@playwright/test'
import lighthouse from 'lighthouse'

const url = process.argv[2] ?? 'http://127.0.0.1:7777/'
const outPath = process.argv[3]
const port = 9333

const browser = await chromium.launch({ args: [`--remote-debugging-port=${String(port)}`] })
try {
  const result = await lighthouse(url, {
    port,
    output: 'json',
    logLevel: 'error',
    onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
  })
  if (result === undefined) throw new Error('Lighthouse returned no result')
  const lhr = result.lhr
  console.log(`Lighthouse ${lhr.lighthouseVersion} (${lhr.configSettings.formFactor}) on ${lhr.finalDisplayedUrl}`)
  for (const [id, category] of Object.entries(lhr.categories)) {
    console.log(`  ${id.padEnd(16)} ${String(Math.round((category.score ?? 0) * 100))}`)
  }
  for (const id of ['first-contentful-paint', 'largest-contentful-paint', 'total-blocking-time', 'cumulative-layout-shift']) {
    console.log(`  ${id.padEnd(26)} ${lhr.audits[id]?.displayValue ?? 'n/a'}`)
  }
  const failing = Object.values(lhr.audits)
    .filter((a) => a.scoreDisplayMode === 'binary' && a.score === 0)
    .map((a) => a.id)
  console.log(`  failing binary audits: ${failing.length > 0 ? failing.join(', ') : 'none'}`)
  if (outPath !== undefined) writeFileSync(outPath, JSON.stringify(lhr, null, 2))
} finally {
  await browser.close()
}
