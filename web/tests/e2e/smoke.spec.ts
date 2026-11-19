import { expect, test } from '@playwright/test'

test('finds the agent through the dev proxy and fits the screen', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'LapRemote' })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText(
    /^Agent \d+\.\d+\.\d+ is running on (Windows|macOS|Linux)\.$/,
  )

  const overflowsHorizontally = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflowsHorizontally).toBe(false)

  await page.screenshot({
    path: testInfo.outputPath(`${testInfo.project.name}-home.png`),
    fullPage: true,
  })
})

test('shows a friendly message when the agent is unreachable', async ({ page }) => {
  await page.route('**/api/health', (route) => route.abort('connectionrefused'))
  await page.goto('/')
  await expect(page.getByRole('status')).toHaveText(
    "Can't reach the agent. Is it running on your laptop?",
  )
  const retry = page.getByRole('button', { name: 'Try again' })
  await expect(retry).toBeVisible()
  const box = await retry.boundingBox()
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)

  await page.unroute('**/api/health')
  await retry.click()
  await expect(page.getByRole('status')).toHaveText(/is running on/)
})
