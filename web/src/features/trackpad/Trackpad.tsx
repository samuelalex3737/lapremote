import { Settings2 } from 'lucide-react'
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { TrackpadController, type PointerSample } from '../../lib/gestures/controller.ts'
import type { SenderOptions } from '../../lib/gestures/sender.ts'
import type { TrackpadSettings } from '../../lib/gestures/settings.ts'
import type { MouseButton } from '../../lib/gestures/trackpad.ts'
import { haptic } from '../../lib/haptics.ts'
import { hintsSeen, markHintsSeen } from '../../lib/hints.ts'
import type { RemoteClient, Session } from '../../lib/ws.ts'
import { IconButton } from '../../ui/Button.tsx'
import { GestureHints } from './GestureHints.tsx'
import { TrackpadSettingsPanel } from './TrackpadSettingsPanel.tsx'
import { useTrackpadSettings } from './useTrackpadSettings.ts'

interface Props {
  client: RemoteClient
  session: Session
}

function senderOptions(client: RemoteClient, session: Session, settings: TrackpadSettings): SenderOptions {
  return {
    send: (type, payload) => {
      client.send(type, payload)
    },
    os: session.os,
    canClick: session.role === 'owner',
    threeFinger: settings.threeFinger,
    onHaptic: (pattern) => haptic(pattern),
  }
}

/** Coalesced events keep fast swipes accurate on 120Hz screens, where supported. */
function samples(e: ReactPointerEvent<HTMLDivElement>): PointerSample[] {
  const rect = e.currentTarget.getBoundingClientRect()
  const native = e.nativeEvent
  const coalesced = 'getCoalescedEvents' in native ? native.getCoalescedEvents() : []
  const events = coalesced.length > 0 ? coalesced : [native]
  return events.map((ev) => ({
    pointerId: e.pointerId,
    x: ev.clientX - rect.left,
    y: ev.clientY - rect.top,
    t: ev.timeStamp,
  }))
}

function sample(e: ReactPointerEvent<HTMLDivElement>): PointerSample {
  const rect = e.currentTarget.getBoundingClientRect()
  return { pointerId: e.pointerId, x: e.clientX - rect.left, y: e.clientY - rect.top, t: performance.now() }
}

export function Trackpad({ client, session }: Props) {
  const [settings, setSettings] = useTrackpadSettings()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [showHints, setShowHints] = useState(() => !hintsSeen())
  const [controller] = useState(() => new TrackpadController(settings, senderOptions(client, session, settings)))
  const surfaceRef = useRef<HTMLDivElement>(null)
  const canClick = session.role === 'owner'

  useEffect(() => {
    controller.configure(settings, senderOptions(client, session, settings))
  }, [controller, client, session, settings])

  useEffect(() => {
    const surface = surfaceRef.current
    if (surface === null) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry !== undefined) controller.resize(entry.contentRect.width, entry.contentRect.height)
    })
    observer.observe(surface)
    return () => {
      observer.disconnect()
    }
  }, [controller])

  useEffect(() => {
    // Safari's own pinch-zoom would fight the pinch gesture.
    const block = (e: Event) => {
      e.preventDefault()
    }
    const onHidden = () => {
      if (document.visibilityState === 'hidden') controller.reset()
    }
    document.addEventListener('gesturestart', block)
    document.addEventListener('visibilitychange', onHidden)
    return () => {
      document.removeEventListener('gesturestart', block)
      document.removeEventListener('visibilitychange', onHidden)
      controller.reset()
    }
  }, [controller])

  const buttonHandlers = (button: MouseButton) => ({
    onPointerDown: (e: ReactPointerEvent<HTMLButtonElement>) => {
      e.preventDefault()
      e.currentTarget.setPointerCapture(e.pointerId)
      haptic(button === 'right' ? 'rightClick' : 'click')
      client.send('input.down', { button })
    },
    onPointerUp: () => {
      client.send('input.up', { button })
    },
    onPointerCancel: () => {
      client.send('input.up', { button })
    },
  })

  const buttonClass =
    'min-h-14 flex-1 touch-none select-none rounded-[var(--radius-control)] bg-[var(--color-surface-strong)] text-sm font-medium ring-1 ring-inset ring-[var(--color-line)] active:bg-[var(--color-line-strong)] landscape:min-h-0'

  return (
    <div className="relative flex min-h-0 flex-1 flex-col gap-3 landscape:flex-row">
      <div
        ref={surfaceRef}
        data-testid="trackpad-surface"
        aria-label="Trackpad"
        role="application"
        className="relative min-h-0 flex-1 touch-none select-none overflow-hidden rounded-[var(--radius-card)] bg-[var(--color-surface)] ring-1 ring-inset ring-[var(--color-line)] [-webkit-touch-callout:none]"
        onPointerDown={(e) => {
          e.preventDefault()
          e.currentTarget.setPointerCapture(e.pointerId)
          if (showHints) {
            setShowHints(false)
            markHintsSeen()
          }
          controller.down(sample(e))
        }}
        onPointerMove={(e) => {
          controller.move(samples(e))
        }}
        onPointerUp={(e) => {
          controller.up(sample(e))
        }}
        onPointerCancel={(e) => {
          controller.cancel(e.pointerId)
        }}
        onContextMenu={(e) => {
          e.preventDefault()
        }}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-8 right-0 w-[12%] border-l border-dashed border-[var(--color-line)]"
        />
        {showHints && <GestureHints />}
      </div>

      {!canClick && (
        <p className="text-center text-sm text-[var(--color-text-secondary)]">
          Guests can move the pointer. Ask the owner for full control.
        </p>
      )}

      <div className="flex gap-3 landscape:w-28 landscape:flex-col">
        {canClick && (
          <>
            <button type="button" className={buttonClass} {...buttonHandlers('left')}>
              Left click
            </button>
            <button type="button" className={buttonClass} {...buttonHandlers('right')}>
              Right click
            </button>
          </>
        )}
        <IconButton
          label="Trackpad settings"
          size="lg"
          className="landscape:self-center"
          onClick={() => {
            setSettingsOpen(true)
          }}
        >
          <Settings2 className="h-6 w-6" />
        </IconButton>
      </div>

      <TrackpadSettingsPanel
        open={settingsOpen}
        settings={settings}
        onChange={setSettings}
        onClose={() => {
          setSettingsOpen(false)
        }}
      />
    </div>
  )
}
