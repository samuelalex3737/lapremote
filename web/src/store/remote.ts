/**
 * The page's single connection to the agent plus Zustand stores that mirror its
 * state for React. Agent toasts and failed requests surface as toasts.
 */
import { create } from 'zustand'
import type { ContextInfo } from '../lib/adaptive.ts'
import { localCredentialStore } from '../lib/credentials.ts'
import { detectDevice, socketUrl } from '../lib/device.ts'
import { MediaStore, type MediaSnapshot } from '../lib/mediaStore.ts'
import type { AgentPayload, Layout, Scene, Shortcut } from '../lib/protocol.ts'
import { RemoteClient, type Snapshot, type SocketLike } from '../lib/ws.ts'
import { useUi } from './ui.ts'

const identity = detectDevice(navigator.userAgent, navigator.maxTouchPoints)

export const client = new RemoteClient({
  url: socketUrl(window.location),
  store: localCredentialStore(),
  createSocket: (url) => {
    const socket = new WebSocket(url)
    // Preview frames arrive as binary messages.
    socket.binaryType = 'arraybuffer'
    // The browser WebSocket satisfies SocketLike; its event objects carry more than we read.
    return socket as unknown as SocketLike
  },
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

/** Launcher shortcuts, scenes, sleep timer and brightness, as last pushed by the agent. */
export interface LaptopExtras {
  shortcuts: Shortcut[] | null
  scenes: Scene[] | null
  timer: AgentPayload<'timer.state'> | null
  brightness: AgentPayload<'brightness.state'> | null
}
export const useExtras = create<LaptopExtras>(() => ({ shortcuts: null, scenes: null, timer: null, brightness: null }))

/** Per-app button layouts and other LapRemote laptops on the network, as pushed by the agent. */
export const useLayouts = create<{ layouts: Layout[] | null }>(() => ({ layouts: null }))
client.on('layouts.state', (p) => {
  useLayouts.setState({ layouts: p.layouts })
})
export type Peer = AgentPayload<'peers.state'>['peers'][number]
export const usePeers = create<{ peers: Peer[] | null }>(() => ({ peers: null }))
client.on('peers.state', (p) => {
  usePeers.setState({ peers: p.peers })
})

/** Text the laptop sent to this phone (tray or dashboard), shown until the person closes it. */
export const useIncoming = create<{ text: string | null; dismiss: () => void }>((set) => ({
  text: null,
  dismiss: () => {
    set({ text: null })
  },
}))
client.on('clipboard.state', (p) => {
  // A reply to clipboard.get is handled by its caller; a push comes without asking.
  if (!expectingClipboard) useIncoming.setState({ text: p.text })
})
let expectingClipboard = false

/** Read the laptop clipboard (owner only). */
export async function readLaptopClipboard(): Promise<string> {
  expectingClipboard = true
  try {
    const reply = await client.request('clipboard.get', {})
    return reply.type === 'clipboard.state' ? reply.payload.text : ''
  } finally {
    expectingClipboard = false
  }
}
client.on('shortcuts.state', (p) => {
  useExtras.setState({ shortcuts: p.shortcuts })
})
client.on('scenes.state', (p) => {
  useExtras.setState({ scenes: p.scenes })
})
client.on('timer.state', (timer) => {
  useExtras.setState({ timer })
})
client.on('brightness.state', (brightness) => {
  useExtras.setState({ brightness })
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
