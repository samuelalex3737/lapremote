import { Maximize2, Monitor } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { haptic } from '../../lib/haptics.ts'
import { clampView, IDENTITY, parseFrame, tapToNormalised, zoomAt, type View } from '../../lib/preview.ts'
import type { AgentPayload } from '../../lib/protocol.ts'
import type { RemoteClient } from '../../lib/ws.ts'
import { Button } from '../../ui/Button.tsx'
import { SegmentedControl, Skeleton } from '../../ui/primitives.tsx'

const FPS = 8
const WIDTH = 480
const TAP_MOVE_PX = 10
const LONG_PRESS_MS = 500

interface Ripple {
  id: number
  x: number
  y: number
  right: boolean
}

interface Touch {
  x: number
  y: number
  startX: number
  startY: number
}

type Meta = AgentPayload<'preview.meta'>

/**
 * Live screen preview: tap to click where you tapped, long-press for a right click,
 * pinch to zoom the picture on the phone for precise taps.
 */
export function ScreenPreview({ client }: { client: RemoteClient }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [monitor, setMonitor] = useState(0)
  const [frame, setFrame] = useState<{ url: string; n: number } | null>(null)
  const [view, setView] = useState<View>(IDENTITY)
  const [ripples, setRipples] = useState<Ripple[]>([])
  const box = useRef<HTMLDivElement>(null)
  const touches = useRef(new Map<number, Touch>())
  const gesture = useRef<{ moved: boolean; longFired: boolean; timer: number | null; pinch: { dist: number; midX: number; midY: number; view: View } | null }>({
    moved: false,
    longFired: false,
    timer: null,
    pinch: null,
  })
  const lastUrl = useRef<string | null>(null)
  const rippleSeq = useRef(0)

  // Start on mount, on reconnect and when the page becomes visible; stop otherwise.
  useEffect(() => {
    const start = () => {
      client.send('preview.start', { fps: FPS, width: WIDTH, monitor })
    }
    const stop = () => {
      client.send('preview.stop', {})
    }
    start()
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') stop()
      else start()
    }
    document.addEventListener('visibilitychange', onVisibility)
    const offAuth = client.on('auth.ok', start)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
      offAuth()
    }
  }, [client, monitor])

  useEffect(() => {
    const offMeta = client.on('preview.meta', (m) => {
      setMeta(m)
    })
    const offFrame = client.onBinary((data) => {
      const parsed = parseFrame(data)
      if (parsed === null) return
      const url = URL.createObjectURL(new Blob([parsed.jpeg as Uint8Array<ArrayBuffer>], { type: 'image/jpeg' }))
      setFrame({ url, n: parsed.frame })
    })
    return () => {
      offMeta()
      offFrame()
      if (lastUrl.current !== null) URL.revokeObjectURL(lastUrl.current)
    }
  }, [client])

  const size = () => {
    const rect = box.current?.getBoundingClientRect()
    return { width: rect?.width ?? 0, height: rect?.height ?? 0 }
  }

  const local = (e: PointerEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const click = (x: number, y: number, right: boolean) => {
    if (meta === null) return
    const point = tapToNormalised(x, y, size(), { width: meta.width, height: meta.height }, view)
    if (point === null) return
    haptic(right ? 'rightClick' : 'click')
    client.send('input.absclick', { x: point.x, y: point.y, monitor, button: right ? 'right' : 'left' })
    rippleSeq.current += 1
    const id = rippleSeq.current
    setRipples((r) => [...r, { id, x, y, right }])
    window.setTimeout(() => {
      setRipples((r) => r.filter((item) => item.id !== id))
    }, 600)
  }

  const clearTimer = () => {
    const g = gesture.current
    if (g.timer !== null) window.clearTimeout(g.timer)
    g.timer = null
  }

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    const p = local(e)
    touches.current.set(e.pointerId, { x: p.x, y: p.y, startX: p.x, startY: p.y })
    const g = gesture.current
    if (touches.current.size === 1) {
      g.moved = false
      g.longFired = false
      g.pinch = null
      clearTimer()
      g.timer = window.setTimeout(() => {
        g.timer = null
        if (!g.moved && touches.current.size === 1) {
          g.longFired = true
          click(p.x, p.y, true)
        }
      }, LONG_PRESS_MS)
    } else if (touches.current.size === 2) {
      clearTimer()
      g.moved = true
      const [a, b] = [...touches.current.values()]
      if (a !== undefined && b !== undefined) {
        g.pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y), midX: (a.x + b.x) / 2, midY: (a.y + b.y) / 2, view }
      }
    }
  }

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const t = touches.current.get(e.pointerId)
    if (t === undefined) return
    const p = local(e)
    const dx = p.x - t.x
    const dy = p.y - t.y
    t.x = p.x
    t.y = p.y
    const g = gesture.current
    if (Math.hypot(p.x - t.startX, p.y - t.startY) > TAP_MOVE_PX) {
      g.moved = true
      clearTimer()
    }
    if (touches.current.size >= 2 && g.pinch !== null) {
      const [a, b] = [...touches.current.values()]
      if (a === undefined || b === undefined) return
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      const midX = (a.x + b.x) / 2
      const midY = (a.y + b.y) / 2
      const zoomed = zoomAt(g.pinch.view, dist / Math.max(1, g.pinch.dist), g.pinch.midX, g.pinch.midY, size())
      setView(clampView({ ...zoomed, tx: zoomed.tx + midX - g.pinch.midX, ty: zoomed.ty + midY - g.pinch.midY }, size()))
    } else if (touches.current.size === 1 && g.moved && view.scale > 1) {
      setView((v) => clampView({ ...v, tx: v.tx + dx, ty: v.ty + dy }, size()))
    }
  }

  const onUp = (e: PointerEvent<HTMLDivElement>) => {
    const t = touches.current.get(e.pointerId)
    touches.current.delete(e.pointerId)
    const g = gesture.current
    if (touches.current.size === 0) {
      clearTimer()
      if (t !== undefined && !g.moved && !g.longFired) click(t.x, t.y, false)
      g.pinch = null
    }
  }

  const monitors = meta?.monitors ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {monitors.length > 1 && (
        <SegmentedControl
          label="Screen"
          options={monitors.map((m) => ({ value: String(m.index), label: m.primary ? `Main (${String(m.index + 1)})` : `Screen ${String(m.index + 1)}` }))}
          value={String(monitor)}
          onChange={(v) => {
            setView(IDENTITY)
            setMonitor(Number(v))
          }}
        />
      )}
      <div
        ref={box}
        data-testid="screen-preview"
        role="application"
        aria-label="Laptop screen. Tap to click, press and hold to right click, pinch to zoom."
        className="relative min-h-0 flex-1 touch-none select-none overflow-hidden rounded-[var(--radius-card)] bg-black ring-1 ring-inset ring-[var(--color-line)]"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onContextMenu={(e) => {
          e.preventDefault()
        }}
      >
        {frame === null ? (
          <Skeleton label="Waiting for the laptop screen" className="absolute inset-3" />
        ) : (
          <img
            src={frame.url}
            alt="Laptop screen"
            draggable={false}
            className="absolute inset-0 h-full w-full origin-top-left object-contain"
            style={{ transform: `translate(${String(view.tx)}px, ${String(view.ty)}px) scale(${String(view.scale)})` }}
            onLoad={() => {
              // Ack once drawn: the agent keeps at most 2 frames in flight.
              client.send('preview.ack', { frame: frame.n })
              if (lastUrl.current !== null && lastUrl.current !== frame.url) URL.revokeObjectURL(lastUrl.current)
              lastUrl.current = frame.url
            }}
          />
        )}
        <AnimatePresence>
          {ripples.map((r) => (
            <motion.span
              key={r.id}
              aria-hidden="true"
              className={`pointer-events-none absolute h-12 w-12 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 ${r.right ? 'border-[var(--color-warn)]' : 'border-white'}`}
              style={{ left: r.x, top: r.y }}
              initial={{ scale: 0.3, opacity: 0.9 }}
              animate={{ scale: 1.4, opacity: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            />
          ))}
        </AnimatePresence>
      </div>
      <div className="flex items-center justify-between gap-3 text-sm text-[var(--color-text-secondary)]">
        <span className="flex items-center gap-2">
          <Monitor className="h-4 w-4" aria-hidden="true" />
          Tap to click · hold for right click
        </span>
        {view.scale > 1 && (
          <Button
            icon={<Maximize2 className="h-4 w-4" aria-hidden="true" />}
            onClick={() => {
              setView(IDENTITY)
            }}
          >
            Fit
          </Button>
        )}
      </div>
    </div>
  )
}
