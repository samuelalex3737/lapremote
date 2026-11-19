import { useSyncExternalStore } from 'react'
import { localCredentialStore } from '../lib/credentials.ts'
import { detectDevice, socketUrl } from '../lib/device.ts'
import { RemoteClient, type Snapshot, type SocketLike } from '../lib/ws.ts'

const identity = detectDevice(navigator.userAgent, navigator.maxTouchPoints)

/** The one connection to the agent for this page. */
export const client = new RemoteClient({
  url: socketUrl(window.location),
  store: localCredentialStore(),
  // The browser WebSocket satisfies SocketLike; its event objects carry more than we read.
  createSocket: (url) => new WebSocket(url) as unknown as SocketLike,
  deviceName: identity.name,
  platform: identity.platform,
})

export function useRemote(): Snapshot {
  return useSyncExternalStore(client.subscribe, client.getSnapshot)
}

/** Read `?pair=123456` once and remove it from the address bar so it never lingers. */
export function takePairCode(): string | null {
  const url = new URL(window.location.href)
  const code = url.searchParams.get('pair')
  if (code === null) return null
  url.searchParams.delete('pair')
  window.history.replaceState(null, '', url.pathname + url.search + url.hash)
  return /^\d{6}$/.test(code) ? code : null
}
