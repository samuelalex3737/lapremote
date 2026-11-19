import { MotionConfig } from 'motion/react'
import { useEffect } from 'react'
import { PairScreen } from '../features/pairing/PairScreen.tsx'
import { client, takePairCode, useConnection } from '../store/remote.ts'
import { ToastHost } from '../ui/Toast.tsx'
import { Shell } from './Shell.tsx'
import { Splash } from './Splash.tsx'

const initialPairCode = takePairCode()

export function App() {
  const status = useConnection((s) => s.status)
  const session = useConnection((s) => s.session)

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

  const pairing = status.kind === 'unpaired' || status.kind === 'pairing'

  return (
    <MotionConfig reducedMotion="user">
      <ToastHost />
      {pairing ? (
        <main className="mx-auto flex h-full max-w-md flex-col justify-center px-4 pt-safe pb-safe">
          <PairScreen
            error={status.kind === 'unpaired' ? status.error : null}
            busy={status.kind === 'pairing'}
            onPair={(code) => {
              client.pair(code)
            }}
          />
        </main>
      ) : session === null ? (
        <Splash status={status} />
      ) : (
        <Shell />
      )}
    </MotionConfig>
  )
}
