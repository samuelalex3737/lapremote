import { describe, expect, it } from 'vitest'
import { movieKeys, suggestMode, type ContextInfo } from '../../src/lib/adaptive.ts'
import { BACKGROUND, accentFrom, contrast, gradientFrom, hslToRgb, rgbToHsl, toCss } from '../../src/lib/color.ts'
import { fractionAt, keyboardStep, timeAt } from '../../src/lib/scrub.ts'

function ctx(patch: Partial<ContextInfo>): ContextInfo {
  return {
    app: 'Brave',
    processName: 'brave.exe',
    windowTitle: '',
    category: 'browser',
    site: 'generic',
    ts: 1,
    ...patch,
  }
}

describe('suggestMode', () => {
  it.each([
    [ctx({ site: 'netflix' }), 'movie', 'Netflix in focus - movie controls'],
    [ctx({ site: 'youtube' }), 'movie', 'YouTube in focus - movie controls'],
    [ctx({ site: 'prime' }), 'movie', 'Prime Video in focus - movie controls'],
    [ctx({ site: 'spotify_web' }), 'music', 'Spotify in focus - music controls'],
    [ctx({ app: 'Spotify', processName: 'Spotify.exe', category: 'music', site: null }), 'music', 'Spotify in focus - music controls'],
    [ctx({ app: 'VLC', processName: 'vlc.exe', category: 'video', site: null }), 'movie', 'VLC in focus - movie controls'],
    [ctx({ app: 'PowerPoint', processName: 'POWERPNT.EXE', category: 'presentation', site: null }), 'presentation', 'PowerPoint in focus - presentation controls'],
  ] as const)('%#: %s', (context, mode, text) => {
    expect(suggestMode(context)).toMatchObject({ mode, text })
  })

  it('has no suggestion for ordinary apps and sites', () => {
    expect(suggestMode(ctx({ site: 'generic' }))).toBeNull()
    expect(suggestMode(ctx({ app: 'Code', processName: 'Code.exe', category: 'other', site: null }))).toBeNull()
    expect(suggestMode(null)).toBeNull()
  })

  it('keys the suggestion by context so dismissals stick until focus changes', () => {
    const a = suggestMode(ctx({ site: 'netflix', windowTitle: 'Episode 1' }))
    const b = suggestMode(ctx({ site: 'netflix', windowTitle: 'Episode 2' }))
    expect(a?.key).toBe(b?.key)
  })
})

describe('movieKeys', () => {
  it('shows skip intro only on Netflix and subtitles only on YouTube', () => {
    expect(movieKeys(ctx({ site: 'netflix' }))).toEqual({ fullscreen: 'f', skipIntro: 's', subtitles: null })
    expect(movieKeys(ctx({ site: 'youtube' }))).toEqual({ fullscreen: 'f', skipIntro: null, subtitles: 'c' })
    expect(movieKeys(ctx({ site: 'prime' }))).toEqual({ fullscreen: 'f', skipIntro: null, subtitles: null })
    expect(movieKeys(null).skipIntro).toBeNull()
  })
})

describe('colour', () => {
  it('round-trips HSL', () => {
    for (const rgb of [[200, 30, 30], [10, 120, 240], [128, 128, 128]] as const) {
      const back = hslToRgb(rgbToHsl(rgb))
      back.forEach((v, i) => {
        expect(Math.abs(v - (rgb[i] ?? 0))).toBeLessThanOrEqual(1)
      })
    }
  })

  it('keeps every accent readable on the dark background (AA 4.5:1)', () => {
    const samples = [
      [0, 0, 0],
      [255, 255, 255],
      [20, 10, 60],
      [200, 30, 30],
      [30, 200, 60],
      [12, 12, 12],
      [90, 40, 160],
    ] as const
    for (const sample of samples) {
      expect(contrast(accentFrom(sample), BACKGROUND)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('builds css strings and gradients', () => {
    expect(toCss([1, 2, 3])).toBe('rgb(1 2 3)')
    expect(toCss([1, 2, 3], 0.5)).toBe('rgb(1 2 3 / 0.5)')
    expect(gradientFrom([200, 30, 30])).toMatch(/^radial-gradient\(/)
  })
})

describe('scrub', () => {
  it('maps pointer to fraction and time', () => {
    expect(fractionAt(150, 100, 200)).toBe(0.25)
    expect(fractionAt(50, 100, 200)).toBe(0)
    expect(fractionAt(400, 100, 200)).toBe(1)
    expect(fractionAt(1, 0, 0)).toBe(0)
    expect(timeAt(0.5, 201)).toBe(100.5)
    expect(keyboardStep(120)).toBe(5)
    expect(keyboardStep(3600)).toBe(36)
  })
})
