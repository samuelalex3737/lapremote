import { useCallback, useEffect, useState } from 'react'
import { describeOs, fetchHealth, type Health } from '../lib/health.ts'

type AgentStatus =
  | { kind: 'checking' }
  | { kind: 'online'; health: Health }
  | { kind: 'offline' }

export function App() {
  const [status, setStatus] = useState<AgentStatus>({ kind: 'checking' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => {
        setStatus({ kind: 'online', health })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.warn('Agent health check failed', error)
          setStatus({ kind: 'offline' })
        }
      })
    return () => {
      controller.abort()
    }
  }, [attempt])

  const retry = useCallback(() => {
    setStatus({ kind: 'checking' })
    setAttempt((n) => n + 1)
  }, [])

  return (
    <main
      className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-6 px-6 text-center"
      style={{
        paddingTop: 'max(1.5rem, env(safe-area-inset-top))',
        paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))',
      }}
    >
      <h1 className="text-4xl font-semibold tracking-tight">LapRemote</h1>
      <p className="text-base text-zinc-300" role="status" aria-live="polite">
        {status.kind === 'checking' && 'Looking for your laptop...'}
        {status.kind === 'online' &&
          `Agent ${status.health.version} is running on ${describeOs(status.health.os)}.`}
        {status.kind === 'offline' && "Can't reach the agent. Is it running on your laptop?"}
      </p>
      {status.kind === 'offline' && (
        <button
          type="button"
          onClick={retry}
          className="min-h-11 rounded-full bg-zinc-100 px-6 text-base font-medium text-zinc-900 active:scale-95"
        >
          Try again
        </button>
      )}
    </main>
  )
}
