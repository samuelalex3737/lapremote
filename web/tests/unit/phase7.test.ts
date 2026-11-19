import { describe, expect, it } from 'vitest'
import { commonShortcuts, liveDiff, modifierLabel } from '../../src/lib/keys.ts'
import type { MediaSession } from '../../src/lib/protocol.ts'
import { endOfMediaSeconds, formatCountdown, remainingSeconds } from '../../src/lib/timer.ts'

describe('liveDiff', () => {
  it.each([
    ['', 'h', [{ kind: 'text', text: 'h' }]],
    ['hel', 'hello', [{ kind: 'text', text: 'lo' }]],
    ['hello', 'hel', [{ kind: 'backspace', count: 2 }]],
    ['hello', 'help', [{ kind: 'backspace', count: 2 }, { kind: 'text', text: 'p' }]],
    ['same', 'same', []],
  ] as const)('%s -> %s', (before, after, edits) => {
    expect(liveDiff(before, after)).toEqual(edits)
  })
})

describe('common shortcuts', () => {
  it('uses Cmd on macOS and Ctrl elsewhere', () => {
    expect(commonShortcuts('macos')[0]).toEqual({ label: 'Copy', key: 'c', modifiers: ['meta'] })
    expect(commonShortcuts('windows')[0]).toEqual({ label: 'Copy', key: 'c', modifiers: ['ctrl'] })
    expect(commonShortcuts('windows').at(-1)).toEqual({ label: 'Alt+Tab', key: 'tab', modifiers: ['alt'] })
    expect(commonShortcuts('macos').at(-1)?.modifiers).toEqual(['meta'])
  })

  it('names modifiers per OS', () => {
    expect(modifierLabel('meta', 'windows')).toBe('Win')
    expect(modifierLabel('meta', 'macos')).toBe('Cmd')
    expect(modifierLabel('alt', 'macos')).toBe('Option')
  })
})

describe('timer helpers', () => {
  const session = (patch: Partial<MediaSession>): MediaSession => ({
    id: 'w1',
    appId: 'x',
    appName: 'X',
    title: 't',
    artist: '',
    album: '',
    artworkId: null,
    artwork: null,
    status: 'playing',
    position: 100,
    duration: 250,
    rate: 1,
    canSeek: true,
    canNext: true,
    canPrev: true,
    updatedAt: 1_000_000,
    ...patch,
  })

  it('computes end of media from the interpolated position', () => {
    expect(endOfMediaSeconds(session({}), 1_010_000)).toBe(140)
    expect(endOfMediaSeconds(session({ duration: null }), 1_010_000)).toBeNull()
    expect(endOfMediaSeconds(null, 1)).toBeNull()
  })

  it('formats countdowns', () => {
    expect(formatCountdown(65)).toBe('1:05')
    expect(formatCountdown(3725)).toBe('1:02:05')
    expect(remainingSeconds(10_000, 4_000)).toBe(6)
    expect(remainingSeconds(null, 4_000)).toBe(0)
  })
})

describe('shortcut helpers', async () => {
  const { makeId, normaliseUrl, visibleShortcuts } = await import('../../src/lib/shortcuts.ts')

  it('makes unique ids', () => {
    expect(makeId('YouTube Music!', [])).toBe('youtube-music')
    expect(makeId('Netflix', ['netflix', 'netflix-2'])).toBe('netflix-3')
    expect(makeId('***', [])).toBe('item')
  })

  it('normalises URLs and refuses other schemes', () => {
    expect(normaliseUrl('netflix.com')).toBe('https://netflix.com/')
    expect(normaliseUrl('http://example.org/a?b=1')).toBe('http://example.org/a?b=1')
    expect(normaliseUrl('javascript:alert(1)')).toBeNull()
    expect(normaliseUrl('file:///etc/passwd')).toBeNull()
    expect(normaliseUrl('not a url')).toBeNull()
  })

  it('hides internal shortcuts', () => {
    const s = (id: string) => ({ id, name: id, kind: 'url' as const, url: 'https://a.b' })
    expect(visibleShortcuts([s('a'), s('_once')]).map((x) => x.id)).toEqual(['a'])
    expect(visibleShortcuts(null)).toEqual([])
  })
})
