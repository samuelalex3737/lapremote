import { expect, test } from '@playwright/test'
import { openPaired } from './helpers.ts'

// The e2e agent reads the laptop's real media sessions and volume (read-only:
// this test never presses play or moves the volume).
test('media panel shows the sessions or "Nothing playing", and the volume', async ({ page }, testInfo) => {
  await openPaired(page, { tab: 'now' })
  const nav = page.getByRole('navigation', { name: 'Main' })
  await expect(nav.getByRole('button', { name: 'Now Playing' })).toHaveAttribute('aria-current', 'page')
  const playback = page.getByRole('button', { name: /^(Play|Pause)$/ }).first()
  await expect(playback.or(page.getByText('Nothing playing'))).toBeVisible()
  await expect(page.getByRole('slider', { name: 'Volume' })).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflow).toBe(false)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-media.png`) })
})
