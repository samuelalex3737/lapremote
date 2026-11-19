/**
 * The page's single connection to the agent plus Zustand stores that mirror its
 * state for React. Agent toasts and failed requests surface as toasts.
 */
import { create } from 'zustand'
import type { ContextInfo } from '../lib/adaptive.ts'
import { localCredentialStore } from '../lib/credentials.ts'
import { detectDevice, socketUrl } from '../lib/device.ts'
import { MediaStore, type MediaSnapshot } from '../lib/mediaStore.ts'
import { RemoteClient, type Snapshot, type SocketLike } from '../lib/ws.ts'
import { useUi } from './ui.ts'

const identity = detectDevice(navigator.userAgent, navigator.maxTouchPoints)

export const client = new RemoteClient({
  url: socketUrl(window.location),
  store: localCredentialStore(),
  // The browser WebSocket satisfies SocketLike; its event objects carry more than we read.
  createSocket: (url) => new WebSocket(url) as unknown as SocketLike,
  deviceName: identity.name,
  platform: identity.platform,
})

export const mediaStore = new MediaStore(client)

export const useConnection = create<Snapshot>(() => client.getSnapshot())
client.subscribe(() => {
  useConnection.setState(client.getSnapshot(), true)
})

export const useMedia = create<MediaSnapshot>(() => mediaStore.getSnapshot())
mediaStore.subscribe(() => {
  useMedia.setState(mediaStore.getSnapshot(), true)
})

/** What is in front on the laptop (context.state), or null until the agent reports it. */
export const useLaptopContext = create<{ context: ContextInfo | null }>(() => ({ context: null }))
client.on('context.state', (context) => {
  useLaptopContext.setState({ context })
})

client.on('toast', (p) => {
  useUi.getState().showToast(p.level, p.message)
})
client.on('ack', (p) => {
  if (!p.ok && p.error != null) useUi.getState().showToast('error', p.error)
})

/** Read `?pair=123456` once and remove it from the address bar so it never lingers. */
export function takePairCode(): string | null {
  const url = new URL(window.location.href)
  const code = url.searchParams.get('pair')
  if (code === null) return null
  url.searchParams.delete('pair')
  window.history.replaceState(null, '', url.pathname + url.search + url.hash)
  return /^\d{6}$/.test(code) ? code : null
}
