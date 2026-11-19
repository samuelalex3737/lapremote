import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { expectNoHorizontalScroll, expectTapTargets, openPaired, openTab } from './helpers.ts'

const TABS = ['Now Playing', 'Trackpad', 'Keys', 'Launch', 'More'] as const

for (const tab of TABS) {
  test(`${tab} tab: screenshot, no horizontal scroll, 44px targets, no serious a11y issues`, async ({ page }, testInfo) => {
    await openPaired(page)
    await openTab(page, tab)
    // Let the slide animation settle before measuring.
    await page.waitForTimeout(500)
    await expectNoHorizontalScroll(page)
    await expectTapTargets(page)
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([])
    await page.screenshot({
      path: testInfo.outputPath(`${testInfo.project.name}-${tab.toLowerCase().replace(' ', '-')}.png`),
    })
  })
}

test('More: every sub-screen opens and goes back', async ({ page }, testInfo) => {
  await openPaired(page)
  await openTab(page, 'More')
  for (const name of ['Scenes', 'Sleep timer', 'Power', 'Ask LapRemote', 'Devices', 'Settings']) {
    await page.getByRole('button', { name: new RegExp(`^${name}`) }).click()
    await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible()
    await expectNoHorizontalScroll(page)
    if (name === 'Settings' || name === 'Devices') {
      await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-more-${name.toLowerCase()}.png`) })
    }
    await page.getByRole('button', { name: 'Back' }).click()
  }
})

test('the pairing screen passes the same checks', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Pair with your laptop' })).toBeVisible()
  await expectNoHorizontalScroll(page)
  await expectTapTargets(page)
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
  expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')).toEqual([])
})

test('swiping left and right changes tabs, but not on the trackpad', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'touch swipes are driven through the Chromium DevTools protocol')
  await openPaired(page, { tab: 'launch' })
  const cdp = await page.context().newCDPSession(page)
  const box = await page.locator('main').boundingBox()
  if (box === null) throw new Error('no main')
  const y = box.y + box.height * 0.6
  const swipe = async (fromX: number, toX: number) => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: fromX, y }] })
    for (let i = 1; i <= 6; i++) {
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x: fromX + ((toX - fromX) * i) / 6, y }],
      })
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await page.waitForTimeout(400)
  }
  const left = () => swipe(box.x + box.width * 0.8, box.x + box.width * 0.2)
  const right = () => swipe(box.x + box.width * 0.2, box.x + box.width * 0.8)
  const nav = page.getByRole('navigation', { name: 'Main' })
  const current = (name: string) => expect(nav.getByRole('button', { name })).toHaveAttribute('aria-current', 'page')

  await left()
  await current('More')
  await right()
  await current('Launch')
  await right()
  await current('Keys')
  await right()
  await current('Trackpad')
  // On the trackpad a swipe is a gesture for the laptop, not navigation.
  await left()
  await current('Trackpad')
})

test('first connection that fails shows the offline splash with a retry', async ({ page }) => {
  await page.routeWebSocket('**/ws', async (ws) => {
    await ws.close({ code: 4000, reason: 'test: agent unreachable' })
  })
  await openPairedNoWait(page)
  await expect(page.getByText("Can't reach your laptop. Is it on the same Wi-Fi?")).toBeVisible()
  await expect(page.getByRole('button', { name: 'Try now' })).toBeVisible()
})

test('works with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await openPaired(page)
  await openTab(page, 'Keys')
  await expect(page.getByRole('heading', { name: 'Keys' })).toBeVisible()
  await openTab(page, 'More')
  await expect(page.getByRole('heading', { name: 'More' })).toBeVisible()
})

test('trackpad uses a side layout in landscape', async ({ page }, testInfo) => {
  const size = page.viewportSize()
  if (size === null) throw new Error('no viewport')
  await page.setViewportSize({ width: size.height, height: size.width })
  await openPaired(page, { tab: 'trackpad' })
  const surface = page.getByTestId('trackpad-surface')
  const left = page.getByRole('button', { name: 'Left click' })
  const surfaceBox = await surface.boundingBox()
  const leftBox = await left.boundingBox()
  if (surfaceBox === null || leftBox === null) throw new Error('missing boxes')
  expect(leftBox.x).toBeGreaterThan(surfaceBox.x + surfaceBox.width - 1)
  await expectNoHorizontalScroll(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-trackpad-landscape.png`) })
})

test('the PWA manifest and iOS meta tags are in place', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.locator('meta[name="apple-mobile-web-app-capable"]')).toHaveAttribute('content', 'yes')
  await expect(page.locator('meta[name="apple-mobile-web-app-status-bar-style"]')).toHaveAttribute('content', 'black-translucent')
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute('href', '/icons/apple-touch-icon.png')
  expect(await page.locator('link[rel="apple-touch-startup-image"]').count()).toBe(7)
  for (const path of ['/icons/icon-192.png', '/icons/icon-512.png', '/icons/maskable-512.png', '/icons/apple-touch-icon.png', '/splash/splash-1179x2556.png']) {
    const res = await request.get(path)
    expect(res.status(), path).toBe(200)
  }
})

async function openPairedNoWait(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    localStorage.setItem('lapremote.credentials.v1', JSON.stringify({ deviceId: 'x', token: 'y' }))
  })
  await page.goto('/')
}
