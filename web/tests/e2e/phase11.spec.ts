import { expect, test, type Page } from '@playwright/test'
import { FakeAgent, context, session } from './fakeAgent.ts'
import { expectNoHorizontalScroll, expectTapTargets } from './helpers.ts'

async function start(page: Page, opts: { ctx?: unknown; sessions?: unknown[]; setup?: (agent: FakeAgent) => void } = {}) {
  const agent = new FakeAgent({ sessions: opts.sessions ?? [session()], context: opts.ctx ?? null })
  opts.setup?.(agent)
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
  const back = page.getByRole('button', { name: 'Back', exact: true })
  if (await back.isVisible()) await back.click()
  await page.getByRole('button', { name: item }).click()
}

test('dark by default; the sun and moon button switches to light and is remembered', async ({ page }, testInfo) => {
  await start(page)
  const html = page.locator('html')
  await expect(html).toHaveAttribute('data-theme', 'dark')
  const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  expect(await bg()).toBe('rgb(7, 7, 11)')
  await page.getByRole('button', { name: 'Switch to light mode' }).click()
  await expect(html).toHaveAttribute('data-theme', 'light')
  expect(await bg()).toBe('rgb(244, 245, 249)')
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#f4f5f9')
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-light.png`) })
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('button', { name: 'Switch to dark mode' })).toBeVisible()
  await more(page, /^Settings/)
  await expect(page.getByRole('switch', { name: /Light mode/ })).toHaveAttribute('aria-checked', 'true')
  await page.getByRole('button', { name: 'Switch to dark mode' }).click()
  await expect(html).toHaveAttribute('data-theme', 'dark')
})

test('send to laptop: text, links, the laptop clipboard and files', async ({ page, browserName, context: browser }, testInfo) => {
  if (browserName === 'chromium') await browser.grantPermissions(['clipboard-read', 'clipboard-write'])
  const agent = await start(page)
  await more(page, /^Send to laptop/)
  const box = page.getByLabel('Text or link')
  await box.fill('hello from the phone')
  await expect(page.getByRole('button', { name: 'Open link' })).toBeDisabled()
  await page.getByRole('button', { name: 'Copy to laptop' }).click()
  await expect.poll(() => agent.of('clipboard.set').map((m) => m.payload.text)).toEqual(['hello from the phone'])

  await box.fill('example.org/page')
  await page.getByRole('button', { name: 'Open link' }).click()
  await expect.poll(() => agent.of('url.open').map((m) => m.payload.url)).toEqual(['https://example.org/page'])

  await page.getByRole('button', { name: "Get the laptop's clipboard" }).click()
  // The laptop clipboard now holds what this phone just sent it.
  await expect(page.getByLabel('Laptop clipboard')).toHaveText('hello from the phone')

  const uploads: { headers: Record<string, string>; size: number }[] = []
  await page.route('**/api/upload', async (route) => {
    const request = route.request()
    uploads.push({ headers: request.headers(), size: (request.postDataBuffer() ?? Buffer.alloc(0)).length })
    await route.fulfill({ json: { ok: true, name: 'holiday photo.png', size: 4 } })
  })
  await page.getByLabel('Files to send').setInputFiles({ name: 'holiday photo.png', mimeType: 'image/png', buffer: Buffer.from([1, 2, 3, 4]) })
  await expect(page.getByRole('list', { name: 'Sent files' })).toContainText('Sent')
  expect(uploads).toHaveLength(1)
  expect(uploads[0]?.headers['x-lapremote-device']).toBe('fake')
  expect(uploads[0]?.headers.authorization).toBe('Bearer fake-token')
  expect(uploads[0]?.headers['x-lapremote-filename']).toBe('holiday%20photo.png')
  // WebKit doesn't expose a file request's body to Playwright; the bytes are checked on Chromium.
  if (browserName === 'chromium') expect(uploads[0]?.size).toBe(4)
  // Credentials never go in the address.
  await expectNoHorizontalScroll(page)
  await expectTapTargets(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-send.png`), fullPage: true })
})

test('text sent from the laptop pops up with a copy button', async ({ page }) => {
  const agent = await start(page)
  agent.push('clipboard.state', { text: 'from the tray', ts: Date.now() })
  const sheet = page.getByRole('dialog', { name: 'From your laptop' })
  await expect(sheet).toContainText('from the tray')
  await expect(sheet.getByRole('button', { name: 'Copy to this phone' })).toBeVisible()
})

test('call buttons: Zoom in front offers them, and Mute presses Alt+A', async ({ page }, testInfo) => {
  const agent = await start(page, { ctx: context({ app: 'Zoom', processName: 'Zoom.exe', windowTitle: 'Zoom Meeting', category: 'other', site: null }) })
  await expect(page.getByText('Zoom call in focus - call buttons')).toBeVisible()
  await page.getByRole('button', { name: 'Switch', exact: true }).click()
  const pad = page.getByRole('group', { name: 'Zoom call buttons' })
  await expect(pad).toBeVisible()
  await pad.getByRole('button', { name: 'Mute' }).click()
  await pad.getByRole('button', { name: 'Leave' }).click()
  await expect
    .poll(() => agent.of('key.press').map((m) => m.payload))
    .toEqual([
      { key: 'a', modifiers: ['alt'] },
      { key: 'q', modifiers: ['alt'] },
    ])
  // On the buttons already: the suggestion goes away.
  await expect(page.getByText('Zoom call in focus - call buttons')).toHaveCount(0)
  await page.getByRole('tab', { name: 'Spotify' }).click()
  await page.getByRole('group', { name: 'Spotify buttons' }).getByRole('button', { name: 'Next' }).click()
  await expect.poll(() => agent.of('media.next').length).toBe(1)
  await expectTapTargets(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-call-buttons.png`) })
})

test('layouts: build a new one in the editor', async ({ page }) => {
  const agent = await start(page)
  await more(page, /^Layouts/)
  await expect(page.getByText('Zoom call')).toBeVisible()
  await page.getByRole('button', { name: 'New layout' }).click()
  const sheet = page.getByRole('dialog', { name: 'New layout' })
  await sheet.getByLabel('Name', { exact: true }).fill('My game')
  await sheet.getByLabel(/App program names/).fill('Game.exe, launcher.exe')
  await sheet.getByLabel('Label for button 1').fill('Jump')
  await sheet.getByLabel('Action for button 1').selectOption('key')
  await sheet.getByLabel('Key for button 1').selectOption('space')
  await sheet.getByRole('button', { name: 'Add button' }).click()
  await sheet.getByLabel('Label for button 2').fill('Back 30')
  await sheet.getByLabel('Action for button 2').selectOption('seek')
  await sheet.getByLabel('Seconds for button 2').fill('-30')
  await sheet.getByRole('button', { name: 'Save layout' }).click()
  await expect(sheet).toBeHidden()
  await expect.poll(() => agent.of('layouts.save').at(-1)?.payload).toEqual({
    layout: {
      id: 'my-game',
      name: 'My game',
      match: { processes: ['Game.exe', 'launcher.exe'], titles: [], sites: [] },
      buttons: [
        { label: 'Jump', icon: 'play', action: { type: 'key', key: 'space', modifiers: [] } },
        { label: 'Back 30', icon: null, action: { type: 'seek', by: -30 } },
      ],
    },
  })
  await expect(page.getByText('My game')).toBeVisible()
})

test('laptops: open one that is online, wake one that is asleep', async ({ page }, testInfo) => {
  const agent = await start(page, {
    setup: (a) => {
      a.peers = [
        { peerId: '0123456789abcdef', name: 'Den PC', url: 'http://192.168.1.40:7777/', online: true, mac: '14:13:33:8C:12:3F', lastSeenAt: Date.now() },
        { peerId: 'fedcba9876543210', name: 'Work laptop', url: 'http://192.168.1.41:7777/', online: false, mac: 'AA:BB:CC:DD:EE:FF', lastSeenAt: Date.now() - 3_600_000 },
      ]
    },
  })
  await more(page, /^Laptops/)
  const list = page.getByRole('list', { name: 'Other laptops' })
  await expect(list).toContainText('Den PC')
  await expect(list).toContainText('Work laptop')
  await expect(list).toContainText('Asleep or off, seen 1 h ago')
  await list.getByRole('button', { name: 'Wake' }).click()
  await expect.poll(() => agent.of('wol.wake').map((m) => m.payload)).toEqual([{ mac: 'AA:BB:CC:DD:EE:FF' }])
  await expectTapTargets(page)
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-laptops.png`) })
  await expect(list.getByRole('button', { name: 'Open' })).toBeVisible()
})

test('launcher: real icons, the app picker and open once', async ({ page }, testInfo) => {
  const icon =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
  const agent = await start(page, {
    setup: (a) => {
      a.shortcuts = [...a.shortcuts, { id: 'twitch', name: 'Twitch', kind: 'url', url: 'https://twitch.tv/', icon: null, image: icon } as never]
    },
  })
  await tab(page, 'Launch')
  await expect(page.getByRole('button', { name: 'Twitch', exact: true }).locator('img')).toHaveAttribute('src', icon)

  await page.getByRole('button', { name: 'Add shortcut' }).click()
  const sheet = page.getByRole('dialog', { name: 'New shortcut' })
  await sheet.getByRole('radio', { name: 'App' }).click()
  await sheet.getByLabel("Search the laptop's apps").fill('spot')
  await sheet.getByRole('list', { name: 'Apps on the laptop' }).getByRole('button', { name: 'Spotify' }).click()
  await expect(sheet.getByText('Opens Spotify')).toBeVisible()
  await expect(sheet.getByLabel('Name')).toHaveValue('Spotify')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect.poll(() => agent.of('shortcuts.save').at(-1)?.payload).toEqual({
    shortcut: { id: 'spotify-2', name: 'Spotify', kind: 'app', app: 'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify', icon: null },
  })

  await page.getByRole('button', { name: 'Open a website' }).click()
  await page.getByRole('dialog', { name: 'Open a website' }).getByLabel('Web address').fill('example.org')
  await page.getByRole('button', { name: 'Open once' }).click()
  await expect.poll(() => agent.of('url.open').map((m) => m.payload.url)).toEqual(['https://example.org/'])
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-launch-icons.png`) })
})

test('lock screen: shows what plays on the laptop and its buttons control it', async ({ page }) => {
  await page.addInitScript(() => {
    try {
    const handlers: Record<string, (d: { seekTime?: number }) => void> = {}
    const state = { metadata: null as unknown, playbackState: 'none', handlers }
    Object.defineProperty(navigator, 'mediaSession', {
      configurable: true,
      value: {
        setActionHandler: (action: string, fn: ((d: { seekTime?: number }) => void) | null) => {
          if (fn === null) Reflect.deleteProperty(handlers, action)
          else handlers[action] = fn
        },
        setPositionState: () => undefined,
        set metadata(m: unknown) {
          state.metadata = m
        },
        get metadata() {
          return state.metadata
        },
        set playbackState(p: string) {
          state.playbackState = p
        },
        get playbackState() {
          return state.playbackState
        },
      },
    })
    ;(window as unknown as { __lock: typeof state }).__lock = state
    if (!('MediaMetadata' in window)) {
      // WebKit here has no MediaMetadata: a plain copy of the fields stands in.
      ;(window as unknown as { MediaMetadata: unknown }).MediaMetadata = function MediaMetadata(this: object, init: object) {
        Object.assign(this, init)
      }
    }
    HTMLMediaElement.prototype.play = function play() {
      return Promise.resolve()
    }
    } catch (error) {
      ;(window as unknown as { __lockError: string }).__lockError = String(error)
    }
  })
  const agent = await start(page, { sessions: [session({ title: 'Midnight City', artist: 'M83', status: 'playing' })] })
  await page.mouse.click(10, 300) // the first tap allows sound
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __lock: { metadata: { title?: string } | null } }).__lock.metadata?.title))
    .toBe('Midnight City')
  expect(await page.evaluate(() => (window as unknown as { __lock: { playbackState: string } }).__lock.playbackState)).toBe('playing')
  await page.evaluate(() => {
    const lock = (window as unknown as { __lock: { handlers: Record<string, (d: { seekTime?: number }) => void> } }).__lock
    lock.handlers.nexttrack?.({})
    lock.handlers.seekto?.({ seekTime: 42 })
  })
  await expect.poll(() => agent.of('media.next').map((m) => m.payload)).toEqual([{ sessionId: 'w1' }])
  await expect.poll(() => agent.of('media.seek').map((m) => m.payload)).toEqual([{ sessionId: 'w1', to: 42 }])
})
