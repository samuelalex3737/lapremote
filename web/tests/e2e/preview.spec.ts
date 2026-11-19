import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { FakeAgent } from './fakeAgent.ts'
import { expectTapTargets, openPaired } from './helpers.ts'
import { e2eHome } from './seed.ts'

async function openScreen(page: Page) {
  const nav = page.getByRole('navigation', { name: 'Main' })
  await nav.getByRole('button', { name: 'Trackpad' }).click()
  await page.getByRole('radio', { name: 'Screen' }).click()
  const image = page.getByRole('img', { name: 'Laptop screen' })
  await expect(image).toBeVisible()
  return image
}

test('frames are acked once drawn, taps click where tapped, hold is a right click', async ({ page }, testInfo) => {
  const agent = new FakeAgent({ sessions: [], context: null })
  await agent.install(page)
  await page.goto('/')
  const image = await openScreen(page)
  await expect.poll(() => agent.of('preview.start').at(-1)?.payload).toEqual({ fps: 8, width: 480, monitor: 0 })
  // React StrictMode may start the stream twice in dev, so any drawn frame counts.
  await expect.poll(() => agent.of('preview.ack').length).toBeGreaterThan(0)

  // The 480x270 frame is letterboxed (object-fit: contain); tap its exact centre.
  const box = await page.getByTestId('screen-preview').boundingBox()
  if (box === null) throw new Error('no preview box')
  const scale = Math.min(box.width / 480, box.height / 270)
  const top = box.y + (box.height - 270 * scale) / 2
  const left = box.x + (box.width - 480 * scale) / 2
  await page.touchscreen.tap(left + 480 * scale * 0.5, top + 270 * scale * 0.5)
  await expect.poll(() => agent.of('input.absclick').length).toBe(1)
  const click = agent.of('input.absclick')[0]?.payload as { x: number; y: number; button: string; monitor: number }
  expect(click.button).toBe('left')
  expect(click.monitor).toBe(0)
  expect(click.x).toBeCloseTo(0.5, 2)
  expect(click.y).toBeCloseTo(0.5, 2)

  // A tap on the letterbox bar does nothing.
  await page.touchscreen.tap(box.x + box.width / 2, box.y + 4)
  await page.waitForTimeout(200)
  expect(agent.of('input.absclick').length).toBe(1)

  await expectTapTargets(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-screen.png`) })

  // Leaving the screen view stops the stream.
  await page.getByRole('radio', { name: 'Trackpad' }).click()
  await expect.poll(() => agent.of('preview.stop').length).toBeGreaterThan(0)
  await expect(image).toHaveCount(0)
})

test('press and hold on the preview is a right click', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'touch holds are driven through the Chromium DevTools protocol')
  const agent = new FakeAgent({ sessions: [], context: null })
  await agent.install(page)
  await page.goto('/')
  await openScreen(page)
  const box = await page.getByTestId('screen-preview').boundingBox()
  if (box === null) throw new Error('no preview box')
  const cdp = await page.context().newCDPSession(page)
  const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point] })
  await page.waitForTimeout(700)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await expect.poll(() => agent.of('input.absclick').map((m) => m.payload.button)).toEqual(['right'])
})

test('several monitors get a picker, and switching restarts the stream on that monitor', async ({ page }) => {
  const agent = new FakeAgent({ sessions: [], context: null })
  agent.monitors = [
    { index: 0, left: 0, top: 0, width: 1920, height: 1080, primary: true },
    { index: 1, left: 1920, top: 0, width: 2560, height: 1440, primary: false },
  ]
  await agent.install(page)
  await page.goto('/')
  await openScreen(page)
  await page.getByRole('radio', { name: 'Screen 2' }).click()
  await expect.poll(() => agent.of('preview.start').at(-1)?.payload).toEqual({ fps: 8, width: 480, monitor: 1 })
})

test('the real agent streams this laptop screen and taps reach the input engine', async ({ page }) => {
  await openPaired(page, { tab: 'trackpad' })
  await page.getByRole('radio', { name: 'Screen' }).click()
  const image = page.getByRole('img', { name: 'Laptop screen' })
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(480)
  const box = await page.getByTestId('screen-preview').boundingBox()
  if (box === null) throw new Error('no preview box')
  const log = () =>
    readFileSync(join(e2eHome(), 'logs', 'agent.log'), 'utf8')
      .split(/\r?\n/)
      .filter((l) => l.includes('"dry_run_input"') && l.includes('"move_to"')).length
  const before = log()
  await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2)
  // The e2e agent runs with --input-dry-run: the absolute click is logged, not performed.
  await expect.poll(log).toBeGreaterThan(before)
})
