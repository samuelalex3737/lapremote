import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { E2E_DEVICE_ID, E2E_TOKEN, e2eHome } from './seed.ts'

interface LogEntry {
  event: string
  action?: string
  type?: string
  ok?: boolean
  key?: string
}

function agentLog(): LogEntry[] {
  const text = readFileSync(join(e2eHome(), 'logs', 'agent.log'), 'utf8')
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line) as LogEntry)
}

async function openTrackpad(page: Page) {
  await page.addInitScript(
    ([deviceId, token]) => {
      localStorage.setItem('lapremote.credentials.v1', JSON.stringify({ deviceId, token }))
      sessionStorage.removeItem('lapremote.hintsSeen')
    },
    [E2E_DEVICE_ID, E2E_TOKEN],
  )
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Connected to ')
  const surface = page.getByTestId('trackpad-surface')
  await expect(surface).toBeVisible()
  return surface
}

test('tap clicks on the laptop, hints disappear after the first touch', async ({ page }, testInfo) => {
  const surface = await openTrackpad(page)
  await expect(page.getByText('Tap with two fingers')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-trackpad.png`) })

  expect(await surface.evaluate((el) => getComputedStyle(el).touchAction)).toBe('none')
  const before = agentLog().filter((e) => e.type === 'input.click' && e.ok === true).length

  const box = await surface.boundingBox()
  if (box === null) throw new Error('surface has no box')
  await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2)

  await expect(page.getByText('Tap with two fingers')).toBeHidden()
  await expect
    .poll(() => agentLog().filter((e) => e.type === 'input.click' && e.ok === true).length)
    .toBeGreaterThan(before)

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflow).toBe(false)
})

test('settings open, change and persist', async ({ page }) => {
  await openTrackpad(page)
  await page.getByRole('button', { name: 'Trackpad settings' }).click()
  const dialog = page.getByRole('dialog', { name: 'Trackpad settings' })
  await expect(dialog).toBeVisible()
  const natural = dialog.getByRole('switch', { name: 'Natural scrolling' })
  await natural.uncheck()
  await dialog.getByRole('button', { name: 'Done' }).click()
  await expect(dialog).toBeHidden()
  const stored = await page.evaluate(() => localStorage.getItem('lapremote.trackpad.v1'))
  expect(JSON.parse(stored ?? '{}')).toMatchObject({ naturalScroll: false })
})

test('one-finger drag moves and two-finger drag scrolls (real touch events)', async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== 'chromium', 'multi-touch is driven through the Chromium DevTools protocol')
  const surface = await openTrackpad(page)
  const box = await surface.boundingBox()
  if (box === null) throw new Error('surface has no box')
  const cdp = await page.context().newCDPSession(page)
  const cx = box.x + box.width / 2
  const cy = box.y + box.height / 2
  type TouchType = 'touchStart' | 'touchMove' | 'touchEnd'
  const touch = async (type: TouchType, points: { x: number; y: number }[]) => {
    await cdp.send('Input.dispatchTouchEvent', {
      type,
      touchPoints: points.map((p, id) => ({ x: p.x, y: p.y, id })),
    })
  }
  const count = (action: string) =>
    agentLog().filter((e) => e.event === 'dry_run_input' && e.action === action).length

  const moves = count('move')
  await touch('touchStart', [{ x: cx, y: cy }])
  for (let i = 1; i <= 10; i++) {
    await touch('touchMove', [{ x: cx + i * 8, y: cy }])
    await page.waitForTimeout(16)
  }
  await touch('touchEnd', [])
  await expect.poll(() => count('move')).toBeGreaterThan(moves)

  const scrolls = count('scroll')
  await touch('touchStart', [
    { x: cx - 40, y: cy },
    { x: cx + 40, y: cy },
  ])
  for (let i = 1; i <= 10; i++) {
    await touch('touchMove', [
      { x: cx - 40, y: cy - i * 8 },
      { x: cx + 40, y: cy - i * 8 },
    ])
    await page.waitForTimeout(16)
  }
  await touch('touchEnd', [])
  await expect.poll(() => count('scroll')).toBeGreaterThan(scrolls)
})
