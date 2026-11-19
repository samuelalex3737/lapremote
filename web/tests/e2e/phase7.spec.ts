import { expect, test, type Page } from '@playwright/test'
import { FakeAgent, session } from './fakeAgent.ts'
import { expectNoHorizontalScroll, expectTapTargets } from './helpers.ts'

async function start(page: Page, sessions: unknown[] = []) {
  const agent = new FakeAgent({ sessions, context: null })
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
  await page.getByRole('button', { name: item }).click()
}

async function checks(page: Page, testInfo: { project: { name: string }; outputPath: (s: string) => string }, name: string) {
  await expectNoHorizontalScroll(page)
  await expectTapTargets(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-${name}.png`), fullPage: true })
}

test('keys: send text, live typing, quick keys, combo builder and shortcuts', async ({ page }, testInfo) => {
  const agent = await start(page)
  await tab(page, 'Keys')
  await page.getByPlaceholder('Text is typed where the cursor is').fill('hello laptop')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect.poll(() => agent.of('key.text').map((m) => m.payload.text)).toEqual(['hello laptop'])

  await page.getByRole('radio', { name: 'Live' }).click()
  const live = page.getByPlaceholder('Start typing')
  await live.fill('hi')
  await live.fill('h')
  await expect.poll(() => agent.of('key.text').map((m) => m.payload.text)).toEqual(['hello laptop', 'hi'])
  await expect.poll(() => agent.of('key.press').map((m) => m.payload.key)).toEqual(['backspace'])

  await page.getByRole('button', { name: 'Start' }).click()
  await page.getByRole('button', { name: 'Copy' }).click()
  await page.getByRole('button', { name: 'Alt+Tab' }).click()
  await page.getByRole('group', { name: 'Modifiers' }).getByRole('button', { name: 'Ctrl' }).click()
  await page.getByRole('group', { name: 'Modifiers' }).getByRole('button', { name: 'Shift' }).click()
  await page.getByLabel('Then press').getByRole('button', { name: 't', exact: true }).click()
  await expect
    .poll(() => agent.of('key.press').slice(1).map((m) => m.payload))
    .toEqual([
      { key: 'esc', modifiers: ['ctrl'] },
      { key: 'c', modifiers: ['ctrl'] },
      { key: 'tab', modifiers: ['alt'] },
      { key: 't', modifiers: ['ctrl', 'shift'] },
    ])
  await checks(page, testInfo, 'keys')
})

test('launch: open, add, open once and delete shortcuts', async ({ page }, testInfo) => {
  const agent = await start(page)
  await tab(page, 'Launch')
  for (const name of ['Netflix', 'YouTube', 'YouTube Music', 'Prime Video', 'Spotify']) {
    await expect(page.getByRole('button', { name, exact: true })).toBeVisible()
  }
  await checks(page, testInfo, 'launch')
  await page.getByRole('button', { name: 'Netflix', exact: true }).click()
  await expect.poll(() => agent.of('launch.open').map((m) => m.payload.shortcutId)).toEqual(['netflix'])

  await page.getByRole('button', { name: 'Add shortcut' }).click()
  const sheet = page.getByRole('dialog', { name: 'New shortcut' })
  await sheet.getByLabel('Name').fill('Twitch')
  await sheet.getByLabel('Web address').fill('twitch.tv')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toBeHidden()
  await expect.poll(() => agent.of('shortcuts.save').at(-1)?.payload).toEqual({
    shortcut: { id: 'twitch', name: 'Twitch', kind: 'url', url: 'https://twitch.tv/', icon: null },
  })
  await expect(page.getByRole('button', { name: 'Twitch', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Open a website' }).click()
  await page.getByRole('dialog', { name: 'Open a website' }).getByLabel('Web address').fill('example.org')
  await page.getByRole('button', { name: 'Open once' }).click()
  await expect.poll(() => agent.of('launch.open').map((m) => m.payload.shortcutId)).toEqual(['netflix', '_once'])
  // The one-off slot never shows up in the grid.
  await expect(page.getByRole('button', { name: 'example.org', exact: true })).toHaveCount(0)

  await page.getByRole('button', { name: 'Edit' }).click()
  await page.getByRole('button', { name: 'Delete Twitch' }).click()
  await expect.poll(() => agent.of('shortcuts.delete').map((m) => m.payload.shortcutId)).toEqual(['twitch'])
  await checks(page, testInfo, 'launch-edit')
})

test('scenes: run a scene and build a new one', async ({ page }, testInfo) => {
  const agent = await start(page)
  await more(page, /^Scenes/)
  await expect(page.getByText('Movie Night')).toBeVisible()
  await expect(page.getByText('Volume 40% · Brightness 60% · Open Netflix')).toBeVisible()
  await page.getByRole('button', { name: 'Run' }).first().click()
  await expect.poll(() => agent.of('scene.run').map((m) => m.payload.sceneId)).toEqual(['movie-night'])
  await checks(page, testInfo, 'scenes')

  await page.getByRole('button', { name: 'New scene' }).click()
  const sheet = page.getByRole('dialog', { name: 'New scene' })
  await sheet.getByLabel('Name').fill('Bedtime')
  await sheet.getByLabel('Step to add').selectOption('volume.set')
  await sheet.getByRole('button', { name: 'Add step' }).click()
  await sheet.getByLabel('Level').fill('15')
  await sheet.getByLabel('Step to add').selectOption('media.pause')
  await sheet.getByRole('button', { name: 'Add step' }).click()
  await sheet.getByRole('button', { name: 'Save scene' }).click()
  await expect.poll(() => agent.of('scenes.save').at(-1)?.payload).toEqual({
    scene: {
      id: 'bedtime',
      name: 'Bedtime',
      steps: [{ type: 'volume.set', level: 15 }, { type: 'media.pause' }],
    },
  })
})

test('sleep timer: presets, then-action, countdown, cancel and end of track', async ({ page }, testInfo) => {
  const agent = await start(page, [session({ duration: 240, position: 60, status: 'playing' })])
  await more(page, /^Sleep timer/)
  await page.getByRole('radio', { name: '+ Lock' }).click()
  await expect(page.getByRole('button', { name: /End of this track \([23]:\d\d\)/ })).toBeEnabled()
  await page.getByRole('button', { name: '30 min' }).click()
  await expect.poll(() => agent.of('timer.set').at(-1)?.payload).toEqual({ mode: 'minutes', minutes: 30, then: 'pause_lock' })
  await expect(page.getByRole('timer')).toHaveText(/^(30:00|29:5\d)$/)
  await checks(page, testInfo, 'timer')
  // The countdown also shows on Now Playing.
  await tab(page, 'Now Playing')
  await expect(page.getByRole('button', { name: /Sleep timer \d+:\d\d/ })).toBeVisible()
  await page.getByRole('button', { name: /Sleep timer/ }).click()
  await page.getByRole('button', { name: 'Cancel timer' }).click()
  await expect.poll(() => agent.of('timer.cancel').length).toBe(1)
  await page.getByRole('button', { name: /End of this track/ }).click()
  await expect.poll(() => agent.of('timer.set').at(-1)?.payload).toEqual({ mode: 'end_of_media', then: 'pause_lock' })
})

test('power: hold to confirm uses a server token; letting go early does nothing', async ({ page }, testInfo) => {
  const agent = await start(page)
  await more(page, /^Power & display/)
  await expect(page.getByRole('slider', { name: 'Screen brightness' })).toHaveValue('70')
  await checks(page, testInfo, 'power')

  const lock = page.getByRole('button', { name: 'Lock (hold to confirm)' })
  await lock.focus()
  await page.keyboard.down('Enter')
  await page.waitForTimeout(400)
  await page.keyboard.up('Enter')
  await page.waitForTimeout(300)
  expect(agent.of('power.prepare')).toEqual([])

  await page.keyboard.down('Enter')
  await page.waitForTimeout(1500)
  await page.keyboard.up('Enter')
  await expect.poll(() => agent.of('power.action').at(-1)?.payload).toEqual({ action: 'lock', confirmToken: 'tok-123' })
  expect(agent.of('power.prepare').map((m) => m.payload.action)).toEqual(['lock'])

  await page.getByRole('slider', { name: 'Screen brightness' }).fill('40')
  await expect.poll(() => agent.of('brightness.set').at(-1)?.payload).toEqual({ level: 40 })
})

test('quick launch shows on Now Playing when nothing plays', async ({ page }) => {
  const agent = await start(page)
  await expect(page.getByText('Nothing playing')).toBeVisible()
  await page.getByRole('button', { name: 'Open YouTube', exact: true }).click()
  await expect.poll(() => agent.of('launch.open').map((m) => m.payload.shortcutId)).toEqual(['youtube'])
})
