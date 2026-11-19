import { describe, expect, it } from 'vitest'
import { ArtworkCache, currentSession, formatTime, positionAt } from '../../src/lib/media.ts'
import type { MediaSession } from '../../src/lib/protocol.ts'

function session(patch: Partial<MediaSession> = {}): MediaSession {
  return {
    id: 'w1',
    appId: 'Spotify',
    appName: 'Spotify',
    title: 'Song',
    artist: 'Band',
    album: 'LP',
    artworkId: null,
    artwork: null,
    status: 'playing',
    position: 30,
    duration: 200,
    rate: 1,
    canSeek: true,
    canNext: true,
    canPrev: true,
    updatedAt: 1_000_000,
    ...patch,
  }
}

describe('positionAt', () => {
  it('interpolates while playing', () => {
    expect(positionAt(session(), 1_005_000)).toBe(35)
    expect(positionAt(session({ rate: 2 }), 1_005_000)).toBe(40)
  })

  it('holds still when paused and clamps to the duration', () => {
    expect(positionAt(session({ status: 'paused' }), 9_000_000)).toBe(30)
    expect(positionAt(session(), 9_000_000)).toBe(200)
    expect(positionAt(session({ position: null }), 1_005_000)).toBeNull()
  })

  it('stays within 1s of the laptop over 5 minutes of playback', () => {
    // The laptop reports position 30 at t0; 300s later it would report 330.
    const after5min = positionAt(session({ duration: 1000 }), 1_000_000 + 300_000)
    expect(Math.abs((after5min ?? 0) - 330)).toBeLessThan(1)
  })
})

describe('formatTime', () => {
  it.each([
    [0, '0:00'],
    [65, '1:05'],
    [3725, '1:02:05'],
    [null, '--:--'],
    [Number.NaN, '--:--'],
  ])('%s -> %s', (input, out) => {
    expect(formatTime(input)).toBe(out)
  })
})

describe('ArtworkCache', () => {
  const state = (sessions: MediaSession[]) => ({ sessions, currentId: null, ts: 1 })

  it('stores images sent once and asks only for unknown ids, once', () => {
    const cache = new ArtworkCache()
    expect(cache.absorb(state([session({ artworkId: 'a', artwork: 'data:a' })]))).toEqual([])
    expect(cache.get('a')).toBe('data:a')
    expect(cache.absorb(state([session({ artworkId: 'a', artwork: null })]))).toEqual([])
    expect(cache.absorb(state([session({ artworkId: 'b', artwork: null })]))).toEqual(['b'])
    expect(cache.absorb(state([session({ artworkId: 'b', artwork: null })]))).toEqual([])
    cache.resolve('b', 'data:b')
    expect(cache.get('b')).toBe('data:b')
  })

  it('can ask again after a missing reply or a reconnect', () => {
    const cache = new ArtworkCache()
    expect(cache.absorb(state([session({ artworkId: 'c', artwork: null })]))).toEqual(['c'])
    cache.resolve('c', null)
    expect(cache.absorb(state([session({ artworkId: 'c', artwork: null })]))).toEqual(['c'])
    cache.resetRequests()
    expect(cache.absorb(state([session({ artworkId: 'c', artwork: null })]))).toEqual(['c'])
  })

  it('evicts the oldest image past its limit', () => {
    const cache = new ArtworkCache(2)
    cache.put('1', 'x')
    cache.put('2', 'y')
    cache.put('3', 'z')
    expect(cache.get('1')).toBeNull()
    expect(cache.get('3')).toBe('z')
  })
})

describe('currentSession', () => {
  it('picks the current id or the first session', () => {
    const a = session({ id: 'a' })
    const b = session({ id: 'b' })
    expect(currentSession({ sessions: [a, b], currentId: 'b' })).toBe(b)
    expect(currentSession({ sessions: [a, b], currentId: 'gone' })).toBe(a)
    expect(currentSession({ sessions: [], currentId: null })).toBeNull()
  })
})
