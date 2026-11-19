import { expect, test, type Page } from '@playwright/test'
import { FakeAgent, context, session } from './fakeAgent.ts'
import { expectNoHorizontalScroll, expectTapTargets } from './helpers.ts'

async function start(page: Page, opts: { ai?: boolean; insecure?: boolean } = {}) {
  const agent = new FakeAgent({ sessions: [session()], context: context(), ai: opts.ai ?? true })
  agent.aiPlans = {
    'pause everything': { reply: 'Paused everything.', actions: [{ type: 'media.pause', payload: {} }], needsConfirm: false },
    'lock my laptop': {
      reply: 'Locking the laptop.',
      actions: [{ type: 'power.action', payload: { action: 'lock' } }],
      needsConfirm: true,
    },
  }
  if (opts.insecure === true) {
    // The test server is on 127.0.0.1, which browsers treat as secure. Pretend it's plain
    // http on a LAN address, which is what the phone sees without HTTPS.
    await page.addInitScript(() => {
      Object.defineProperty(window, 'isSecureContext', { value: false })
    })
  }
  await agent.install(page)
  await page.goto('/')
  await expect(page.getByRole('status').first()).toContainText('Connected to ')
  return agent
}

async function openAi(page: Page) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'More' }).click()
  await page.getByRole('button', { name: /^Ask LapRemote/ }).click()
}

test('ai: shows the laptop reason when the model is not ready', async ({ page }) => {
  await start(page, { ai: false })
  await openAi(page)
  await expect(page.getByText("The AI assistant isn't available")).toBeVisible()
  await expect(page.getByText('Not available in this version yet.')).toBeVisible()
})

test('ai: ask by chip and by typing, see the steps and the result', async ({ page }, testInfo) => {
  const agent = await start(page)
  await openAi(page)
  // Netflix in the foreground with something playing: streaming suggestions.
  await expect(page.getByRole('group', { name: 'Suggestions' }).getByRole('button', { name: 'Next episode' })).toBeVisible()
  await page.getByRole('group', { name: 'Suggestions' }).getByRole('button', { name: 'Pause everything' }).click()
  await expect.poll(() => agent.of('ai.command').map((m) => m.payload.text)).toEqual(['Pause everything'])
  await expect(page.getByText("I can't do that.")).toBeVisible()

  await page.getByLabel('Ask your laptop').fill('pause everything')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText('Paused everything.')).toBeVisible()
  const steps = page.getByRole('list', { name: 'Steps' }).last()
  await expect(steps.getByText('Pause everything')).toBeVisible()
  await expect(steps.getByLabel('done')).toBeVisible()
  await expectNoHorizontalScroll(page)
  await expectTapTargets(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-ai.png`), fullPage: true })
})

test('ai: risky plans wait for confirmation, cancel sends approve false', async ({ page }, testInfo) => {
  const agent = await start(page)
  await openAi(page)
  await page.getByLabel('Ask your laptop').fill('lock my laptop')
  await page.getByRole('button', { name: 'Send' }).click()
  const sheet = page.getByRole('dialog', { name: 'Do this on your laptop?' })
  await expect(sheet).toBeVisible()
  await expect(sheet.getByText('Lock the laptop')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-ai-confirm.png`) })
  await sheet.getByRole('button', { name: 'Cancel' }).click()
  await expect.poll(() => agent.of('ai.confirm').map((m) => m.payload)).toEqual([{ planId: 'plan-1', approve: false }])
  await expect(page.getByText('Cancelled. Nothing was done.')).toBeVisible()

  await page.getByLabel('Ask your laptop').fill('lock my laptop')
  await page.getByRole('button', { name: 'Send' }).click()
  await sheet.getByRole('button', { name: 'Do it' }).click()
  await expect.poll(() => agent.of('ai.confirm').at(-1)?.payload).toEqual({ planId: 'plan-2', approve: true })
  await expect(page.getByRole('list', { name: 'Steps' }).last().getByLabel('done')).toBeVisible()
})

test('secure page: mic button and air mouse are offered', async ({ page, context: browser, browserName }) => {
  if (browserName === 'chromium') {
    await browser.grantPermissions(['accelerometer', 'gyroscope'])
  } else {
    // iOS shows its own motion prompt, which automation can't tap: answer it with "Allow".
    await page.addInitScript(() => {
      Object.defineProperty(DeviceMotionEvent, 'requestPermission', { value: () => Promise.resolve('granted') })
    })
  }
  await page.addInitScript(() => {
    localStorage.setItem('lapremote.trackpad.v1', JSON.stringify({ airMouse: true }))
  })
  const agent = await start(page)
  await openAi(page)
  const hasSpeech = await page.evaluate(() => 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window)
  await expect(page.getByRole('button', { name: 'Speak' })).toHaveCount(hasSpeech ? 1 : 0)

  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Trackpad' }).click()
  await page.getByRole('radio', { name: 'Air mouse' }).click()
  await page.getByRole('button', { name: 'Turn on air mouse' }).click()
  const pad = page.getByRole('button', { name: 'Hold to point' })
  await pad.focus()
  await page.keyboard.down('Space')
  // Turning the phone right (negative alpha) moves the cursor right.
  await page.evaluate(async () => {
    for (let i = 0; i < 6; i += 1) {
      // WebKit can't construct DeviceMotionEvent, so send a plain event with the same fields.
      const e = new Event('devicemotion')
      Object.defineProperty(e, 'rotationRate', { value: { alpha: -60, beta: 0, gamma: 0 } })
      window.dispatchEvent(e)
      await new Promise((r) => setTimeout(r, 20))
    }
  })
  await page.keyboard.up('Space')
  await expect.poll(() => agent.of('input.move').reduce((sum, m) => sum + Number(m.payload.dx), 0)).toBeGreaterThan(0)
  const moves = agent.of('input.move').length
  // Released: motion no longer moves the cursor.
  await page.evaluate(() => {
    const e = new Event('devicemotion')
    Object.defineProperty(e, 'rotationRate', { value: { alpha: -60, beta: 0, gamma: 0 } })
    window.dispatchEvent(e)
  })
  await page.waitForTimeout(100)
  expect(agent.of('input.move').length).toBe(moves)
  await page.getByRole('button', { name: 'Click', exact: true }).click()
  await expect.poll(() => agent.of('input.click').map((m) => m.payload.button)).toEqual(['left'])
})

test('plain http: no mic, and the air mouse explains how to get HTTPS', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    localStorage.setItem('lapremote.trackpad.v1', JSON.stringify({ airMouse: true }))
  })
  await start(page, { insecure: true })
  await openAi(page)
  await expect(page.getByRole('button', { name: 'Speak' })).toHaveCount(0)
  await expect(page.getByText('A mic button appears here on HTTPS.', { exact: false })).toBeVisible()

  await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: 'Trackpad' }).click()
  await page.getByRole('radio', { name: 'Air mouse' }).click()
  await expect(page.getByText('The air mouse needs HTTPS')).toBeVisible()
  await expect(page.getByText('tailscale serve 7777')).toBeVisible()
  await expectNoHorizontalScroll(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-needs-https.png`), fullPage: true })

  await page.getByRole('radio', { name: 'Trackpad' }).click()
  await page.getByRole('button', { name: 'Trackpad settings' }).click()
  await expect(page.getByRole('switch', { name: /Air mouse/ })).toBeVisible()
  await expect(page.getByText('Point the phone to move the cursor. Needs HTTPS.')).toBeVisible()
})
