import { motion } from 'motion/react'
import type { Status } from '../lib/ws.ts'
import { client } from '../store/remote.ts'
import { Button } from '../ui/Button.tsx'
import { Logo } from '../ui/Logo.tsx'

/** First connection: logo while connecting, a friendly retry when the laptop can't be reached. */
export function Splash({ status }: { status: Status }) {
  const offline = status.kind === 'offline'
  return (
    <main className="flex h-full flex-col items-center justify-center gap-6 px-4 pt-safe pb-safe text-center">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 20 }}
      >
        <Logo size={88} />
      </motion.div>
      {offline ? (
        <div role="status" className="flex flex-col items-center gap-3">
          <p className="text-lg font-semibold">Can't reach your laptop. Is it on the same Wi-Fi?</p>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Trying again in {Math.ceil(status.retryInMs / 1000)}s
          </p>
          <Button
            variant="secondary"
            onClick={() => {
              client.reconnectNow()
            }}
          >
            Try now
          </Button>
        </div>
      ) : (
        <p role="status" className="text-base text-[var(--color-text-secondary)]">
          Connecting to your laptop...
        </p>
      )}
    </main>
  )
}
