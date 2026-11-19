import { useEffect, useState } from 'react'
import { DevicesList } from '../features/devices/DevicesList.tsx'
import { MediaPanel } from '../features/nowplaying/MediaPanel.tsx'
import { PairScreen } from '../features/pairing/PairScreen.tsx'
import { Trackpad } from '../features/trackpad/Trackpad.tsx'
import { client, mediaStore, takePairCode, useRemote } from './client.ts'
import { Toaster } from './Toaster.tsx'

const initialPairCode = takePairCode()

type View = 'media' | 'trackpad' | 'devices'

const VIEWS: [View, string][] = [
  ['media', 'Media'],
  ['trackpad', 'Trackpad'],
  ['devices', 'Devices'],
]

export function App() {
  const { status, session, latencyMs } = useRemote()
  const [view, setView] = useState<View>('media')

  useEffect(() => {
    if (initialPairCode !== null) client.pair(initialPairCode)
    else client.start()
    const wake = () => {
      if (document.visibilityState === 'visible') client.reconnectNow()
    }
    window.addEventListener('online', wake)
    document.addEventListener('visibilitychange', wake)
    return () => {
      window.removeEventListener('online', wake)
      document.removeEventListener('visibilitychange', wake)
      client.stop()
    }
  }, [])

  const connected = status.kind === 'connected' && session !== null

  return (
    <main
      className="mx-auto flex h-dvh max-w-md flex-col gap-4 px-4"
      style={{
        paddingTop: 'max(1rem, env(safe-area-inset-top))',
        paddingBottom: 'max(1rem, env(safe-area-inset-bottom))',
      }}
    >
      <Toaster client={client} />

      {(status.kind === 'unpaired' || status.kind === 'pairing') && (
        <div className="flex flex-1 flex-col justify-center text-center">
          <PairScreen
            error={status.kind === 'unpaired' ? status.error : null}
            busy={status.kind === 'pairing'}
            onPair={(code) => {
              client.pair(code)
            }}
          />
        </div>
      )}

      {status.kind === 'connecting' && (
        <div className="flex flex-1 items-center justify-center">
          <p role="status" className="text-lg text-zinc-300">
            Connecting to your laptop...
          </p>
        </div>
      )}

      {status.kind === 'offline' && (
        <div role="status" className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
          <p className="text-lg font-medium">Can't reach your laptop. Is it on the same Wi-Fi?</p>
          <p className="text-sm text-zinc-400">
            Trying again in {Math.ceil(status.retryInMs / 1000)}s
          </p>
        </div>
      )}

      {connected && (
        <>
          <header className="flex items-center justify-between gap-3">
            <p
              role="status"
              className="truncate rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-medium text-emerald-200"
            >
              Connected to {session.hostName}
              {latencyMs !== null && ` · ${String(latencyMs)}ms`}
            </p>
          </header>
          <nav className="flex gap-2" aria-label="Sections">
            {VIEWS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-pressed={view === id}
                className={`min-h-11 flex-1 rounded-full border px-4 text-sm font-medium ${
                  view === id ? 'border-white/40 bg-white/15' : 'border-white/10'
                }`}
                onClick={() => {
                  setView(id)
                }}
              >
                {label}
              </button>
            ))}
          </nav>

          {view === 'media' && (
            <div className="flex-1 overflow-y-auto">
              <MediaPanel client={client} store={mediaStore} />
            </div>
          )}
          {view === 'trackpad' && <Trackpad client={client} session={session} />}
          {view === 'devices' && (
            <div className="flex flex-1 flex-col gap-6 overflow-y-auto">
              <p className="text-base text-zinc-300">
                {session.role === 'owner'
                  ? "You're the owner of this laptop."
                  : "You're a guest. The owner can give you full control."}
              </p>
              {session.role === 'owner' && (
                <DevicesList client={client} selfId={session.deviceId} />
              )}
              <button
                type="button"
                className="min-h-11 self-start text-sm text-zinc-400 underline underline-offset-4"
                onClick={() => {
                  client.forget()
                }}
              >
                Forget this laptop on this phone
              </button>
            </div>
          )}
        </>
      )}
    </main>
  )
}
