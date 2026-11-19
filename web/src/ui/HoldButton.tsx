import { useEffect, useRef, useState, type ReactNode } from 'react'
import { haptic } from '../lib/haptics.ts'

interface Props {
  label: string
  /** How long the press must be held. */
  holdMs?: number
  onConfirm: () => void
  icon?: ReactNode
  tone?: 'danger' | 'accent'
  disabled?: boolean
}

const RADIUS = 26
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/**
 * Hold-to-confirm: the action fires only after the button is held for `holdMs`,
 * with a progress ring. Releasing early cancels. Keyboard users hold Enter or Space.
 */
export function HoldButton({ label, holdMs = 1200, onConfirm, icon, tone = 'danger', disabled }: Props) {
  const [progress, setProgress] = useState(0)
  const start = useRef<number | null>(null)
  const frame = useRef<number | null>(null)

  const stop = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    start.current = null
    setProgress(0)
  }

  // Timing uses the animation-frame timestamps, so nothing reads the clock during render.
  const tick = (now: number) => {
    start.current ??= now
    const p = Math.min(1, (now - start.current) / holdMs)
    setProgress(p)
    if (p >= 1) {
      haptic('dragLock')
      stop()
      onConfirm()
      return
    }
    frame.current = requestAnimationFrame(tick)
  }

  const begin = () => {
    if (disabled || frame.current !== null) return
    haptic('tick')
    start.current = null
    frame.current = requestAnimationFrame(tick)
  }

  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current)
    },
    [],
  )

  const color = tone === 'danger' ? 'var(--color-danger)' : 'var(--color-accent)'

  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={`${label} (hold to confirm)`}
      className="relative flex min-h-[72px] w-full touch-none select-none items-center gap-4 rounded-[var(--radius-card)] bg-[var(--color-surface)] px-4 text-left ring-1 ring-inset ring-[var(--color-line)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        begin()
      }}
      onPointerUp={stop}
      onPointerCancel={stop}
      onPointerLeave={stop}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) {
          e.preventDefault()
          begin()
        }
      }}
      onKeyUp={stop}
      onContextMenu={(e) => {
        e.preventDefault()
      }}
    >
      <span className="relative flex h-14 w-14 shrink-0 items-center justify-center">
        <svg viewBox="0 0 60 60" className="absolute inset-0 -rotate-90" aria-hidden="true">
          <circle cx="30" cy="30" r={RADIUS} fill="none" stroke="var(--color-line-strong)" strokeWidth="4" />
          <circle
            cx="30"
            cy="30"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - progress)}
          />
        </svg>
        <span style={{ color }}>{icon}</span>
      </span>
      <span className="flex flex-col">
        <span className="text-base font-semibold">{label}</span>
        <span className="text-sm text-[var(--color-text-secondary)]">
          {progress > 0 ? 'Keep holding...' : 'Hold to confirm'}
        </span>
      </span>
    </button>
  )
}
