import { describe, expect, it } from 'vitest'
import {
  CREDENTIALS_KEY,
  localCredentialStore,
  memoryCredentialStore,
} from '../../src/lib/credentials.ts'
import { detectDevice, socketUrl } from '../../src/lib/device.ts'

const IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
const PIXEL =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36'
const ANDROID_REDUCED =
  'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36'
const IPAD_DESKTOP_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15'

describe('detectDevice', () => {
  it('recognises phones', () => {
    expect(detectDevice(IPHONE)).toEqual({ name: 'iPhone', platform: 'ios' })
    expect(detectDevice(PIXEL)).toEqual({ name: 'Pixel 8', platform: 'android' })
    expect(detectDevice(ANDROID_REDUCED)).toEqual({ name: 'Android phone', platform: 'android' })
    expect(detectDevice(IPAD_DESKTOP_UA, 5)).toEqual({ name: 'iPad', platform: 'ios' })
    expect(detectDevice(IPAD_DESKTOP_UA, 0)).toEqual({ name: 'Browser', platform: 'other' })
  })
})

describe('socketUrl', () => {
  it('follows the page scheme and host', () => {
    expect(socketUrl({ protocol: 'http:', host: '192.168.1.20:7777' })).toBe(
      'ws://192.168.1.20:7777/ws',
    )
    expect(socketUrl({ protocol: 'https:', host: 'box.ts.net' })).toBe('wss://box.ts.net/ws')
  })
})

class MemoryStorage implements Storage {
  private map = new Map<string, string>()
  broken = false
  get length() {
    return this.map.size
  }
  clear() {
    this.map.clear()
  }
  getItem(key: string) {
    if (this.broken) throw new Error('blocked')
    return this.map.get(key) ?? null
  }
  key(index: number) {
    return [...this.map.keys()][index] ?? null
  }
  removeItem(key: string) {
    this.map.delete(key)
  }
  setItem(key: string, value: string) {
    if (this.broken) throw new Error('blocked')
    this.map.set(key, value)
  }
}

describe('credential stores', () => {
  it('round-trips through localStorage', () => {
    const storage = new MemoryStorage()
    const store = localCredentialStore(storage)
    expect(store.load()).toBeNull()
    store.save({ deviceId: 'd', token: 't' })
    expect(store.load()).toEqual({ deviceId: 'd', token: 't' })
    store.clear()
    expect(storage.getItem(CREDENTIALS_KEY)).toBeNull()
  })

  it('ignores corrupt or blocked storage', () => {
    const storage = new MemoryStorage()
    storage.setItem(CREDENTIALS_KEY, '{"deviceId":1}')
    const store = localCredentialStore(storage)
    expect(store.load()).toBeNull()
    storage.broken = true
    expect(store.load()).toBeNull()
    expect(() => {
      store.save({ deviceId: 'd', token: 't' })
    }).not.toThrow()
  })

  it('memory store', () => {
    const store = memoryCredentialStore()
    store.save({ deviceId: 'a', token: 'b' })
    expect(store.load()).toEqual({ deviceId: 'a', token: 'b' })
    store.clear()
    expect(store.load()).toBeNull()
  })
})
