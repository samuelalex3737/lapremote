import { describe, expect, it } from 'vitest'
import { BACKGROUND, LIGHT_BACKGROUND, accentFrom, contrast, gradientFrom } from '../../src/lib/color.ts'
import { asLink } from '../../src/lib/copy.ts'
import { buttonMessage, describeAction, layoutId, matchLayout, splitList } from '../../src/lib/layouts.ts'
import { lockActionMessage, lockMetadata, silentWavDataUrl } from '../../src/lib/lockscreen.ts'
import { layoutSchema, type Layout, type MediaSession } from '../../src/lib/protocol.ts'
import { DEFAULT_LAYOUTS } from '../e2e/defaultLayouts.ts'

const layouts: Layout[] = DEFAULT_LAYOUTS.map((l) => layoutSchema.parse(l))

function context(patch: Partial<{ processName: string; windowTitle: string; site: 'youtube' | 'netflix' | null; app: string }>) {
  return {
    app: 'App',
    processName: 'app.exe',
    windowTitle: '',
    category: 'other' as const,
    site: null,
    ts: 0,
    ...patch,
  }
}

describe('layouts', () => {
  it('every default layout passes the protocol schema', () => {
    expect(layouts.map((l) => l.id)).toEqual(['zoom', 'teams', 'meet', 'vlc', 'spotify', 'youtube'])
  })

  it('matches by process name, site or window title, ignoring case', () => {
    expect(matchLayout(layouts, context({ processName: 'Zoom.exe' }))?.id).toBe('zoom')
    expect(matchLayout(layouts, context({ processName: 'ms-teams.exe' }))?.id).toBe('teams')
    expect(matchLayout(layouts, context({ processName: 'chrome.exe', windowTitle: 'Meet - abc-defg-hij - Google Chrome' }))?.id).toBe(
      'meet',
    )
    expect(matchLayout(layouts, context({ processName: 'brave.exe', site: 'youtube' }))?.id).toBe('youtube')
    expect(matchLayout(layouts, context({ processName: 'notepad.exe', windowTitle: 'notes' }))).toBeNull()
    expect(matchLayout(null, context({}))).toBeNull()
    expect(matchLayout(layouts, null)).toBeNull()
  })

  it('buttons send the existing messages only', () => {
    expect(buttonMessage({ type: 'key', key: 'a', modifiers: ['alt'] })).toEqual({
      type: 'key.press',
      payload: { key: 'a', modifiers: ['alt'] },
    })
    expect(buttonMessage({ type: 'key', key: 'space' })).toEqual({ type: 'key.press', payload: { key: 'space', modifiers: [] } })
    expect(buttonMessage({ type: 'media', command: 'next' })).toEqual({ type: 'media.next', payload: {} })
    expect(buttonMessage({ type: 'seek', by: -10 })).toEqual({ type: 'media.seek', payload: { by: -10 } })
    expect(buttonMessage({ type: 'volume', delta: 5 })).toEqual({ type: 'volume.step', payload: { delta: 5 } })
    expect(buttonMessage({ type: 'launch', shortcutId: 'netflix' })).toEqual({
      type: 'launch.open',
      payload: { shortcutId: 'netflix' },
    })
  })

  it('describes actions per OS', () => {
    const name = (id: string) => (id === 'netflix' ? 'Netflix' : id)
    expect(describeAction({ type: 'key', key: 'm', modifiers: ['ctrl', 'shift'] }, 'windows', name)).toBe('Ctrl+Shift+M')
    expect(describeAction({ type: 'key', key: 'm', modifiers: ['meta', 'shift'] }, 'macos', name)).toBe('Cmd+Shift+M')
    expect(describeAction({ type: 'key', key: 'enter' }, 'windows', name)).toBe('Enter')
    expect(describeAction({ type: 'seek', by: -10 }, 'windows', name)).toBe('Back 10s')
    expect(describeAction({ type: 'volume', delta: 5 }, 'windows', name)).toBe('Volume up 5')
    expect(describeAction({ type: 'launch', shortcutId: 'netflix' }, 'windows', name)).toBe('Open Netflix')
  })

  it('makes unique ids and clean lists', () => {
    expect(layoutId('My Game!', layouts)).toBe('my-game')
    expect(layoutId('Zoom', layouts)).toBe('zoom-2')
    expect(layoutId('!!!', layouts)).toBe('layout')
    expect(splitList(' vlc.exe , , game.exe,')).toEqual(['vlc.exe', 'game.exe'])
    expect(splitList('a, bb', 2)).toEqual(['bb'])
  })
})

describe('lock screen', () => {
  it('maps every lock-screen button to a media message for the session on screen', () => {
    expect(lockActionMessage('play', 'w1')).toEqual({ type: 'media.play', payload: { sessionId: 'w1' } })
    expect(lockActionMessage('pause', 'w1')).toEqual({ type: 'media.pause', payload: { sessionId: 'w1' } })
    expect(lockActionMessage('stop', null)).toEqual({ type: 'media.pause', payload: {} })
    expect(lockActionMessage('nexttrack', 'w1')).toEqual({ type: 'media.next', payload: { sessionId: 'w1' } })
    expect(lockActionMessage('previoustrack', 'w1')).toEqual({ type: 'media.prev', payload: { sessionId: 'w1' } })
    expect(lockActionMessage('seekbackward', 'w1')).toEqual({ type: 'media.seek', payload: { sessionId: 'w1', by: -10 } })
    expect(lockActionMessage('seekforward', 'w1')).toEqual({ type: 'media.seek', payload: { sessionId: 'w1', by: 10 } })
    expect(lockActionMessage('seekto', 'w1', { seekTime: 42.5 })).toEqual({
      type: 'media.seek',
      payload: { sessionId: 'w1', to: 42.5 },
    })
    expect(lockActionMessage('seekto', 'w1', { seekTime: -1 })).toBeNull()
    expect(lockActionMessage('seekto', 'w1', {})).toBeNull()
  })

  it('shows the title, artist and artwork', () => {
    const session = { title: 'Song', artist: '', album: 'Album', appName: 'Spotify' } as MediaSession
    expect(lockMetadata(session, 'data:image/jpeg;base64,AAA')).toEqual({
      title: 'Song',
      artist: 'Spotify',
      album: 'Album',
      artwork: [{ src: 'data:image/jpeg;base64,AAA', sizes: '256x256', type: 'image/jpeg' }],
    })
    expect(lockMetadata({ ...session, title: '' }, null).title).toBe('Spotify')
  })

  it('makes a valid one-second silent WAV', () => {
    const url = silentWavDataUrl()
    expect(url.startsWith('data:audio/wav;base64,')).toBe(true)
    const bytes = Uint8Array.from(atob(url.split(',')[1] ?? ''), (c) => c.charCodeAt(0))
    expect(String.fromCharCode(...bytes.slice(0, 4))).toBe('RIFF')
    expect(String.fromCharCode(...bytes.slice(8, 12))).toBe('WAVE')
    expect(bytes.length).toBe(44 + 8000)
    expect(bytes.slice(44).every((b) => b === 128)).toBe(true)
  })
})

describe('send to laptop', () => {
  it.each([
    ['https://example.org/a?b=1', 'https://example.org/a?b=1'],
    ['example.org', 'https://example.org/'],
    ['youtube.com/watch?v=x', 'https://youtube.com/watch?v=x'],
    ['http://intranet.local/x', 'http://intranet.local/x'],
    ['hello there', null],
    ['javascript:alert(1)', null],
    ['file:///C:/Windows', null],
    ['ftp://example.org', null],
    ['localhost', null],
    ['', null],
  ])('%s -> %s', (text, link) => {
    expect(asLink(text)).toBe(link)
  })
})

describe('light mode colours', () => {
  it('keeps the artwork accent readable on the light background', () => {
    for (let hue = 0; hue < 360; hue += 30) {
      for (const sample of [
        [255, 240, 240],
        [20, 20, 25],
        [Math.round(128 + 127 * Math.cos((hue * Math.PI) / 180)), 120, 200],
      ] as [number, number, number][]) {
        expect(contrast(accentFrom(sample, 'light'), LIGHT_BACKGROUND)).toBeGreaterThanOrEqual(4.5)
        expect(contrast(accentFrom(sample, 'dark'), BACKGROUND)).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it('uses a pale wash in light mode', () => {
    expect(gradientFrom([200, 30, 30], 'light')).toMatch(/^radial-gradient\(/)
    expect(gradientFrom([200, 30, 30], 'light')).not.toBe(gradientFrom([200, 30, 30], 'dark'))
  })
})
