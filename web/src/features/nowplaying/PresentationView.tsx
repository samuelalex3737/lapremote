import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw, Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { PRESENTATION_KEYS } from '../../lib/adaptive.ts'
import { haptic } from '../../lib/haptics.ts'
import { formatTime } from '../../lib/media.ts'
import type { KeyName } from '../../lib/protocol.ts'
import { client, useConnection, useLaptopContext } from '../../store/remote.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/primitives.tsx'

function press(key: KeyName) {
  client.send('key.press', { key, modifiers: [] })
}

/** Elapsed talk time, kept on the phone (it survives switching tabs while mounted). */
function useStopwatch() {
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [banked, setBanked] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (startedAt === null) return
    const timer = setInterval(() => {
      setNow(Date.now())
    }, 500)
    return () => {
      clearInterval(timer)
    }
  }, [startedAt])
  const elapsed = banked + (startedAt !== null ? Math.max(0, now - startedAt) : 0)
  return {
    running: startedAt !== null,
    seconds: elapsed / 1000,
    start: () => {
      const t = Date.now()
      setNow(t)
      setStartedAt(t)
    },
    pause: () => {
      if (startedAt !== null) setBanked(elapsed)
      setStartedAt(null)
    },
    reset: () => {
      setBanked(0)
      setStartedAt(null)
    },
  }
}

export function PresentationView() {
  const owner = useConnection((s) => s.session?.role === 'owner')
  const context = useLaptopContext((s) => s.context)
  const watch = useStopwatch()

  if (!owner) {
    return (
      <Card>
        <p className="text-[var(--color-text-secondary)]">Only the owner can control slides.</p>
      </Card>
    )
  }

  const next = () => {
    haptic('click')
    if (!watch.running && watch.seconds === 0) watch.start()
    press(PRESENTATION_KEYS.next)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 short:gap-2 land:grid land:grid-cols-2 land:grid-rows-[auto_1fr] land:gap-2">
      {context?.category === 'presentation' && (
        <p className="truncate text-sm text-[var(--color-text-secondary)] land:hidden">
          {context.app}
          {context.windowTitle !== '' && ` · ${context.windowTitle}`}
        </p>
      )}
      <button
        type="button"
        className="flex min-h-32 flex-1 items-center justify-center gap-3 rounded-[var(--radius-card)] land:row-span-2 land:min-h-0 bg-[var(--color-text)] text-2xl font-semibold text-[var(--color-bg)] outline-none active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        onClick={next}
      >
        Next slide
        <ChevronRight className="h-8 w-8" aria-hidden="true" />
      </button>
      <div className="flex gap-3">
        <Button
          size="lg"
          className="flex-1"
          icon={<ChevronLeft className="h-5 w-5" aria-hidden="true" />}
          onClick={() => {
            press(PRESENTATION_KEYS.previous)
          }}
        >
          Previous
        </Button>
        <Button
          size="lg"
          className="flex-1"
          icon={<Square className="h-5 w-5" aria-hidden="true" />}
          onClick={() => {
            press(PRESENTATION_KEYS.blank)
          }}
        >
          Blank screen
        </Button>
      </div>
      <Card className="flex items-center justify-between gap-3 short:py-2 land:flex-col land:items-start land:justify-center land:py-2">
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Elapsed</span>
          <span className="text-3xl font-semibold tabular-nums" role="timer" aria-live="off">
            {formatTime(watch.seconds)}
          </span>
        </div>
        <div className="flex gap-2">
          <Button
            icon={watch.running ? <Pause className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
            onClick={watch.running ? watch.pause : watch.start}
          >
            {watch.running ? 'Pause' : 'Start'}
          </Button>
          <Button icon={<RotateCcw className="h-4 w-4" aria-hidden="true" />} onClick={watch.reset}>
            Reset
          </Button>
        </div>
      </Card>
    </div>
  )
}
