import { useEffect } from 'react'
import { DevicesList } from '../features/devices/DevicesList.tsx'
import { PairScreen } from '../features/pairing/PairScreen.tsx'
import { client, takePairCode, useRemote } from './client.ts'

const initialPairCode = takePairCode()

export function App() {
  const { status, session, latencyMs } = useRemote()

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

  return (
    <main
      className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-8 px-4 text-center"
      style={{
        paddingTop: 'max(1.5rem, env(safe-area-inset-top))',
        paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))',
      }}
    >
      {(status.kind === 'unpaired' || status.kind === 'pairing') && (
        <PairScreen
          error={status.kind === 'unpaired' ? status.error : null}
          busy={status.kind === 'pairing'}
          onPair={(code) => {
            client.pair(code)
          }}
        />
      )}

      {status.kind === 'connecting' && (
        <p role="status" className="text-lg text-zinc-300">
          Connecting to your laptop...
        </p>
      )}

      {status.kind === 'offline' && (
        <div role="status" className="flex flex-col gap-2">
          <p className="text-lg font-medium">Can't reach your laptop. Is it on the same Wi-Fi?</p>
          <p className="text-sm text-zinc-400">
            Trying again in {Math.ceil(status.retryInMs / 1000)}s
          </p>
        </div>
      )}

      {status.kind === 'connected' && session !== null && (
        <div className="flex flex-col gap-6">
          <p
            role="status"
            className="mx-auto rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-medium text-emerald-200"
          >
            Connected to {session.hostName}
            {latencyMs !== null && ` · ${String(latencyMs)}ms`}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">LapRemote</h1>
          <p className="text-base text-zinc-300">
            {session.role === 'owner'
              ? "You're the owner of this laptop."
              : "You're a guest. The owner can give you full control."}
          </p>
          {session.role === 'owner' && <DevicesList client={client} selfId={session.deviceId} />}
          <button
            type="button"
            className="min-h-11 text-sm text-zinc-400 underline underline-offset-4"
            onClick={() => {
              client.forget()
            }}
          >
            Forget this laptop on this phone
          </button>
        </div>
      )}
    </main>
  )
}
