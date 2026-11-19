import { Hand, MousePointerClick } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AIR_REST, DEFAULT_AIR, airStep, requestMotionPermission, type AirState } from '../../lib/airmouse.ts'
import { haptic } from '../../lib/haptics.ts'
import type { RemoteClient, Session } from '../../lib/ws.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/primitives.tsx'
import { isSecure } from '../../lib/secure.ts'
import { NeedsHttps } from '../secure/NeedsHttps.tsx'
import { useTrackpadSettings } from './useTrackpadSettings.ts'

type Access = 'unknown' | 'granted' | 'denied' | 'missing'

/**
 * Point the phone to move the cursor. Motion only counts while the clutch is held,
 * so putting the phone down never drags the pointer away.
 */
function AirSurface({ client, session }: { client: RemoteClient; session: Session }) {
  const [settings] = useTrackpadSettings()
  const [access, setAccess] = useState<Access>('unknown')
  const [holding, setHolding] = useState(false)
  const pending = useRef({ dx: 0, dy: 0 })
  const frame = useRef<number | null>(null)
  const state = useRef<AirState>(AIR_REST)
  const last = useRef<number | null>(null)
  const canClick = session.role === 'owner'

  useEffect(() => {
    if (!holding || access !== 'granted') return
    state.current = AIR_REST
    last.current = null
    const flush = () => {
      frame.current = null
      const { dx, dy } = pending.current
      if (dx === 0 && dy === 0) return
      pending.current = { dx: 0, dy: 0 }
      client.send('input.move', { dx, dy })
    }
    const onMotion = (e: DeviceMotionEvent) => {
      const rate = e.rotationRate
      if (rate === null) return
      const now = e.timeStamp
      const dt = last.current === null ? 0 : now - last.current
      last.current = now
      const step = airStep(rate, dt, state.current, { ...DEFAULT_AIR, pxPerDegree: settings.airSpeed })
      state.current = step.state
      pending.current = { dx: pending.current.dx + step.dx, dy: pending.current.dy + step.dy }
      frame.current ??= requestAnimationFrame(flush)
    }
    window.addEventListener('devicemotion', onMotion)
    return () => {
      window.removeEventListener('devicemotion', onMotion)
      if (frame.current !== null) cancelAnimationFrame(frame.current)
      frame.current = null
      flush()
    }
  }, [holding, access, client, settings.airSpeed])

  if (access !== 'granted') {
    return (
      <Card className="flex flex-col gap-3">
        <p className="font-medium">Point your phone at the laptop to move the cursor.</p>
        <p className="text-sm text-[var(--color-text-secondary)]">
          Hold it like a TV remote, screen up. The cursor only moves while you hold the button.
        </p>
        {access === 'denied' && (
          <p className="text-sm text-[var(--color-danger)]">Motion access was blocked. Allow it in your browser settings.</p>
        )}
        {access === 'missing' && (
          <p className="text-sm text-[var(--color-danger)]">This phone doesn't report motion to the browser.</p>
        )}
        <Button
          variant="primary"
          size="lg"
          onClick={() => {
            void requestMotionPermission().then((ok) => {
              if (!ok) {
                setAccess('DeviceMotionEvent' in window ? 'denied' : 'missing')
                return
              }
              setAccess('granted')
            })
          }}
        >
          Turn on air mouse
        </Button>
      </Card>
    )
  }

  const release = () => {
    setHolding(false)
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <button
        type="button"
        aria-pressed={holding}
        aria-label="Hold to point"
        className={`flex min-h-56 flex-1 touch-none select-none flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] ring-1 ring-inset transition-colors ${
          holding
            ? 'bg-[var(--color-accent)]/20 ring-[var(--color-accent)]'
            : 'bg-[var(--color-surface)] ring-[var(--color-line)]'
        }`}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          haptic('tick')
          setHolding(true)
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onLostPointerCapture={release}
        onKeyDown={(e) => {
          if (e.key === ' ' || e.key === 'Enter') setHolding(true)
        }}
        onKeyUp={release}
      >
        <Hand className="h-10 w-10" aria-hidden="true" />
        <span className="text-lg font-medium">{holding ? 'Pointing...' : 'Hold to point'}</span>
      </button>
      {canClick && (
        <div className="flex gap-3">
          <Button
            className="flex-1"
            size="lg"
            icon={<MousePointerClick className="h-5 w-5" aria-hidden="true" />}
            onClick={() => {
              client.send('input.click', { button: 'left' })
            }}
          >
            Click
          </Button>
          <Button
            className="flex-1"
            size="lg"
            onClick={() => {
              client.send('input.click', { button: 'right' })
            }}
          >
            Right click
          </Button>
        </div>
      )}
    </div>
  )
}

export function AirMouse({ client, session }: { client: RemoteClient; session: Session }) {
  if (!isSecure()) return <NeedsHttps feature="The air mouse" />
  return <AirSurface client={client} session={session} />
}
