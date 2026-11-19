import { expect, type Page } from '@playwright/test'
import { E2E_DEVICE_ID, E2E_TOKEN } from './seed.ts'

/** Open the app already paired (seeded device) and wait until it is connected. */
export async function openPaired(page: Page, options: { hints?: boolean; tab?: string } = {}) {
  await page.addInitScript(
    (o: { deviceId: string; token: string; hints: boolean; tab: string }) => {
      localStorage.setItem('lapremote.credentials.v1', JSON.stringify({ deviceId: o.deviceId, token: o.token }))
      if (o.tab !== '') localStorage.setItem('lapremote.tab', o.tab)
      else localStorage.removeItem('lapremote.tab')
      if (o.hints) sessionStorage.removeItem('lapremote.hintsSeen')
      else sessionStorage.setItem('lapremote.hintsSeen', '1')
    },
    { deviceId: E2E_DEVICE_ID, token: E2E_TOKEN, hints: options.hints === true, tab: options.tab ?? '' },
  )
  await page.goto('/')
  await expect(page.getByRole('status').first()).toContainText('Connected to ')
}

export async function openTab(page: Page, name: 'Now Playing' | 'Trackpad' | 'Keys' | 'Launch' | 'More') {
  const nav = page.getByRole('navigation', { name: 'Main' })
  await nav.getByRole('button', { name }).click()
  await expect(nav.getByRole('button', { name })).toHaveAttribute('aria-current', 'page')
}

export async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(overflow).toBe(false)
}

/** Every visible button, input, select and link is at least 44x44 CSS px. */
export async function expectTapTargets(page: Page) {
  const small = await page.evaluate(() => {
    const out: string[] = []
    for (const el of document.querySelectorAll<HTMLElement>('button, a, input, select, textarea, [role="switch"]')) {
      const r = el.getBoundingClientRect()
      const style = getComputedStyle(el)
      if (r.width === 0 || r.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue
      if (el.closest('[aria-hidden="true"]') !== null) continue
      if (r.height < 43.5 || r.width < 43.5) {
        out.push(`${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent).trim().slice(0, 30)}" ${String(Math.round(r.width))}x${String(Math.round(r.height))}`)
      }
    }
    return out
  })
  expect(small).toEqual([])
}
