import { describe, expect, it } from 'vitest'
import { describeAction, namesFrom, suggestions } from '../../src/lib/ai.ts'
import { AIR_REST, DEFAULT_AIR, airStep } from '../../src/lib/airmouse.ts'
import type { AiAction, MediaSession } from '../../src/lib/protocol.ts'

const names = namesFrom(
  [{ id: 'youtube', name: 'YouTube', kind: 'url', url: 'https://www.youtube.com/', icon: null }],
  [{ id: 'movie-night', name: 'Movie Night' }],
  [{ id: 'w1', appName: 'Spotify', status: 'playing' } as MediaSession],
)

describe('describeAction', () => {
  it.each<[AiAction, string]>([
    [{ type: 'media.pause', payload: {} }, 'Pause everything'],
    [{ type: 'media.pause', payload: { sessionId: 'w1' } }, 'Pause (Spotify)'],
    [{ type: 'media.seek', payload: { by: -120 } }, 'Back 2 min'],
    [{ type: 'media.seek', payload: { by: 30 } }, 'Forward 30 s'],
    [{ type: 'media.seek', payload: { to: 95 } }, 'Jump to 1:35'],
    [{ type: 'volume.set', payload: { level: 30 } }, 'Volume 30%'],
    [{ type: 'volume.step', payload: { delta: -10 } }, 'Volume down 10'],
    [{ type: 'volume.mute', payload: { muted: false } }, 'Unmute'],
    [{ type: 'power.action', payload: { action: 'sleep' } }, 'Put the laptop to sleep'],
    [{ type: 'launch.open', payload: { shortcutId: 'youtube' } }, 'Open YouTube'],
    [{ type: 'scene.run', payload: { sceneId: 'movie-night' } }, 'Run Movie Night'],
    [{ type: 'timer.set', payload: { mode: 'minutes', minutes: 40, then: 'pause_sleep' } }, 'Sleep timer 40 min, then pause and sleep'],
    [{ type: 'timer.set', payload: { mode: 'end_of_media', then: 'pause' } }, 'Sleep timer at the end of this, then pause'],
    [{ type: 'key.press', payload: { key: 't', modifiers: ['ctrl', 'shift'] } }, 'Press Ctrl+Shift+T'],
    [{ type: 'key.press', payload: { key: 'enter' } }, 'Press Enter'],
    [{ type: 'key.text', payload: { text: 'lofi beats' } }, 'Type "lofi beats"'],
    [{ type: 'wait', payload: { ms: 4000 } }, 'Wait 4 s'],
  ])('%j', (action, label) => {
    expect(describeAction(action, names)).toBe(label)
  })

  it('falls back to the id for unknown names and shortens long text', () => {
    expect(describeAction({ type: 'launch.open', payload: { shortcutId: 'gone' } }, names)).toBe('Open gone')
    expect(describeAction({ type: 'key.text', payload: { text: 'x'.repeat(60) } }, names)).toBe(`Type "${'x'.repeat(40)}..."`)
  })
})

describe('suggestions', () => {
  const playing = [{ id: 'w1', status: 'playing' } as MediaSession]
  const ctx = (site: string | null, category = 'browser') =>
    ({ app: 'Brave', processName: 'brave.exe', windowTitle: '', category, site, ts: 0 }) as never

  it('fits a streaming site', () => {
    expect(suggestions(ctx('netflix'), playing, null)).toEqual(['Next episode', 'Go back 30 seconds', 'Pause everything', 'Volume 30'])
  })
  it('offers YouTube search when nothing plays', () => {
    expect(suggestions(null, [], [{ id: 'youtube' } as never])).toEqual(['Open YouTube and search lofi beats', 'Sleep the laptop in 30 minutes'])
  })
  it('never offers more than four', () => {
    expect(suggestions(ctx('youtube'), playing, null)).toHaveLength(4)
  })
})

describe('airStep', () => {
  const rate = (alpha: number, beta: number) => ({ alpha, beta, gamma: 0 })

  it('ignores tremor inside the dead zone', () => {
    const out = airStep(rate(2, -2.5), 16, AIR_REST)
    expect(out.dx).toBe(0)
    expect(out.dy).toBe(0)
  })

  it('turning left moves left and tilting up moves up', () => {
    const out = airStep(rate(30, 30), 16, AIR_REST, { ...DEFAULT_AIR, smoothing: 1 })
    expect(out.dx).toBeLessThan(0)
    expect(out.dy).toBeLessThan(0)
    // (30 - 3 dead zone) deg/s * 0.016 s * 14 px/deg
    expect(out.dx).toBeCloseTo(-27 * 0.016 * 14)
  })

  it('smooths towards a steady rate', () => {
    let state = AIR_REST
    const dxs: number[] = []
    for (let i = 0; i < 20; i += 1) {
      const out = airStep(rate(-40, 0), 16, state)
      state = out.state
      dxs.push(out.dx)
    }
    expect(dxs[0]).toBeLessThan(dxs[19] ?? 0)
    expect(dxs[19]).toBeCloseTo(37 * 0.016 * 14, 1)
  })

  it('caps long gaps between samples and handles missing rates', () => {
    const long = airStep(rate(-100, 0), 5000, AIR_REST, { ...DEFAULT_AIR, smoothing: 1 })
    expect(long.dx).toBeCloseTo(97 * 0.1 * 14)
    expect(airStep({ alpha: null, beta: null, gamma: null }, 16, AIR_REST).dx).toBe(0)
  })
})
