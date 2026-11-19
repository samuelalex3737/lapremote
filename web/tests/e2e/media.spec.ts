import { expect, test } from '@playwright/test'
import { E2E_DEVICE_ID, E2E_TOKEN } from './seed.ts'

// The e2e agent reads the laptop's real media sessions and volume (read-only:
// this test never presses play or moves the volume).
test('media panel shows the sessions or "Nothing playing", and the volume', async ({ page }, testInfo) => {
  await page.addInitScript(
    ([deviceId, token]) => {
      localStorage.setItem('lapremote.credentials.v1', JSON.stringify({ deviceId, token }))
    },
    [E2E_DEVICE_ID, E2E_TOKEN],
  )
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Connected to ')
  await expect(page.getByRole('button', { name: 'Media' })).toHaveAttribute('aria-pressed', 'true')
  const playback = page.getByRole('button', { name: /^(Play|Pause)$/ }).first()
  await expect(playback.or(page.getByText('Nothing playing'))).toBeVisible()
  await expect(page.getByText('Volume', { exact: true })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflow).toBe(false)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-media.png`) })
})
