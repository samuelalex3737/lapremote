import { expect, test, type Page } from '@playwright/test'
import { E2E_DEVICE_ID, E2E_DEVICE_NAME, E2E_TOKEN } from './seed.ts'

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflow).toBe(false)
}

test('resumes a paired phone over the WebSocket and shows latency', async ({ page }, testInfo) => {
  await page.addInitScript(
    ([deviceId, token]) => {
      localStorage.setItem('lapremote.credentials.v1', JSON.stringify({ deviceId, token }))
    },
    [E2E_DEVICE_ID, E2E_TOKEN],
  )
  await page.goto('/')
  const status = page.getByRole('status')
  await expect(status).toContainText('Connected to ')
  await expect(status).toHaveText(/^Connected to .+ · \d+ms$/)
  await page.getByRole('button', { name: 'Devices' }).click()
  await expect(page.getByText("You're the owner of this laptop.")).toBeVisible()
  await expect(page.getByText(`${E2E_DEVICE_NAME} (this phone)`)).toBeVisible()
  await noHorizontalScroll(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-connected.png`) })
})

test('a wrong code from the QR link shows a friendly error and is removed from the URL', async ({
  page,
}, testInfo) => {
  await page.goto('/?pair=000001')
  await expect(page.getByRole('alert')).toHaveText(
    "That code didn't work. Check the code on your laptop and try again.",
  )
  expect(page.url()).not.toContain('pair=')
  await noHorizontalScroll(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-pair-error.png`) })
})

test('the pairing form only accepts six digits', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Pair with your laptop' })).toBeVisible()
  const input = page.getByLabel('Pairing code')
  const button = page.getByRole('button', { name: 'Pair' })
  await input.fill('12a34')
  await expect(input).toHaveValue('1234')
  await expect(button).toBeDisabled()
  await input.fill('123456')
  await expect(button).toBeEnabled()
  const box = await button.boundingBox()
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
})

test('a revoked token sends the phone back to pairing', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      'lapremote.credentials.v1',
      JSON.stringify({ deviceId: 'nope', token: 'not-a-real-token' }),
    )
  })
  await page.goto('/')
  await expect(page.getByRole('alert')).toHaveText(
    'This phone was unpaired from your laptop. Pair it again.',
  )
  const stored = await page.evaluate(() => localStorage.getItem('lapremote.credentials.v1'))
  expect(stored).toBeNull()
})
