import { expect, test, type Page } from '@playwright/test'
import { FakeAgent, context, session } from './fakeAgent.ts'

// Visible areas of real screens, including what the browser bars leave over: a small Android
// phone in Chrome, an iPhone 15 in Safari, a big phone, an installed app, a tablet and
// phones held sideways. Every main screen must fit each one without scrolling.
const SIZES = [
  { name: 'small-phone', width: 360, height: 600 },
  { name: 'iphone-safari', width: 393, height: 659 },
  { name: 'phone-chrome', width: 390, height: 720 },
  { name: 'big-phone', width: 430, height: 860 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'landscape', width: 780, height: 360 },
  { name: 'small-landscape', width: 640, height: 320 },
]

async function start(page: Page, opts: { sessions?: unknown[]; ctx?: unknown } = {}) {
  const agent = new FakeAgent({
    sessions: opts.sessions ?? [session(), session({ id: 'w2', appName: 'Brave', title: 'KSI Reacts To The Funniest Videos', artist: 'KSIClips', duration: 4500, position: 1171 })],
    context: opts.ctx ?? context(),
    ai: true,
  })
  await agent.install(page)
  await page.goto('/')
  await expect(page.getByRole('status').first()).toContainText('Connected to ')
  return agent
}

async function tab(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name }).click()
}

async function more(page: Page, item: RegExp) {
  await tab(page, 'More')
  const back = page.getByRole('button', { name: 'Back' })
  if (await back.isVisible()) await back.click()
  await page.getByRole('button', { name: item }).click()
}

/** How many CSS pixels the current tab would need to scroll. 0 means it fits. */
async function overflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const scroller = document.querySelector<HTMLElement>('main > div')
    if (scroller === null) return -1
    return Math.max(0, scroller.scrollHeight - scroller.clientHeight)
  })
}

async function fits(
  page: Page,
  name: string,
  testInfo: { project: { name: string }; outputPath: (s: string) => string },
  size: string,
) {
  await page.waitForTimeout(400)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-${size}-${name}.png`) })
  expect.soft(await overflow(page), `${name} should fit on one screen`).toBe(0)
}

for (const size of SIZES) {
  test(`every main screen fits without scrolling: ${size.name} (${String(size.width)}x${String(size.height)})`, async ({ page }, testInfo) => {
  // Eleven screens with a screenshot each: more than the default 30 s under a full parallel run.
  test.setTimeout(120_000)
  await page.setViewportSize({ width: size.width, height: size.height })
  await start(page)
  await fits(page, 'now-music', testInfo, size.name)
  await page.getByRole('radio', { name: 'Movie' }).click()
  await page.getByRole('tab', { name: 'Brave' }).click()
  await fits(page, 'now-movie', testInfo, size.name)
  await page.getByRole('radio', { name: 'Slides' }).click()
  await fits(page, 'now-slides', testInfo, size.name)
  await tab(page, 'Trackpad')
  await fits(page, 'trackpad', testInfo, size.name)
  await tab(page, 'Keys')
  await fits(page, 'keys', testInfo, size.name)
  await tab(page, 'Launch')
  await fits(page, 'launch', testInfo, size.name)
  await tab(page, 'More')
  await fits(page, 'more', testInfo, size.name)
  await more(page, /^Power & display/)
  await fits(page, 'power', testInfo, size.name)
  await more(page, /^Sleep timer/)
  await fits(page, 'timer', testInfo, size.name)
  await more(page, /^Scenes/)
  await fits(page, 'scenes', testInfo, size.name)
  await more(page, /^Ask LapRemote/)
  await fits(page, 'ai', testInfo, size.name)
})
}
