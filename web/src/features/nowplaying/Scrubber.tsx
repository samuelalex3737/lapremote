import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { haptic } from '../../lib/haptics.ts'
import { formatTime } from '../../lib/media.ts'
import { fractionAt, keyboardStep, timeAt } from '../../lib/scrub.ts'

interface Props {
  position: number | null
  duration: number | null
  canSeek: boolean
  onSeek: (seconds: number) => void
}

/** Live position with drag-to-seek; the time previews while dragging and seeks on release. */
export function Scrubber({ position, duration, canSeek, onSeek }: Props) {
  const track = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const seekable = canSeek && duration !== null && duration > 0
  const shown = dragging ?? position
  const fraction = duration !== null && duration > 0 && shown !== null ? Math.min(1, shown / duration) : 0

  const at = (e: PointerEvent<HTMLDivElement>) => {
    const rect = track.current?.getBoundingClientRect()
    if (rect === undefined || duration === null) return 0
    return timeAt(fractionAt(e.clientX, rect.left, rect.width), duration)
  }

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!seekable || position === null) return
    const step = keyboardStep(duration)
    const target = e.key === 'ArrowRight' ? position + step : e.key === 'ArrowLeft' ? position - step : null
    if (target === null) return
    e.preventDefault()
    onSeek(Math.min(duration, Math.max(0, target)))
  }

  return (
    <div className="flex flex-col gap-1.5" data-no-swipe>
      <div
        ref={track}
        role="slider"
        tabIndex={seekable ? 0 : -1}
        aria-label="Playback position"
        aria-valuemin={0}
        aria-valuemax={duration ?? 0}
        aria-valuenow={Math.round(shown ?? 0)}
        aria-valuetext={`${formatTime(shown)} of ${formatTime(duration)}`}
        aria-disabled={!seekable}
        className={`relative flex h-11 touch-none items-center outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${seekable ? 'cursor-pointer' : ''} rounded-full`}
        onKeyDown={onKey}
        onPointerDown={(e) => {
          if (!seekable) return
          e.currentTarget.setPointerCapture(e.pointerId)
          haptic('tick')
          setDragging(at(e))
        }}
        onPointerMove={(e) => {
          if (dragging !== null) setDragging(at(e))
        }}
        onPointerUp={(e) => {
          if (dragging === null) return
          const target = at(e)
          setDragging(null)
          haptic('click')
          onSeek(target)
        }}
        onPointerCancel={() => {
          setDragging(null)
        }}
      >
        <span className="absolute inset-x-0 h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-strong)]">
          <span className="block h-full rounded-full bg-[var(--color-text)]" style={{ width: `${String(fraction * 100)}%` }} />
        </span>
        {seekable && (
          <span
            className={`absolute h-4 w-4 -translate-x-1/2 rounded-full bg-white shadow transition-transform ${dragging !== null ? 'scale-150' : ''}`}
            style={{ left: `${String(fraction * 100)}%` }}
          />
        )}
      </div>
      <div className="flex justify-between text-xs tabular-nums text-[var(--color-text-secondary)]">
        <span>{formatTime(shown)}</span>
        <span>{duration !== null ? `-${formatTime(Math.max(0, duration - (shown ?? 0)))}` : formatTime(null)}</span>
      </div>
    </div>
  )
}
