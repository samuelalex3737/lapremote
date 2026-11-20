import { Clock3, MoonStar } from 'lucide-react'
import { useClock } from '../../app/useClock.ts'
import { haptic } from '../../lib/haptics.ts'
import { currentSession } from '../../lib/media.ts'
import type { AgentPayload } from '../../lib/protocol.ts'
import { endOfMediaSeconds, formatCountdown, remainingSeconds, TIMER_PRESETS } from '../../lib/timer.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, useExtras, useMedia } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, SegmentedControl, Skeleton } from '../../ui/primitives.tsx'

type Then = AgentPayload<'timer.state'>['then'] & string

const THEN_OPTIONS = [
  { value: 'pause', label: 'Pause' },
  { value: 'pause_lock', label: '+ Lock' },
  { value: 'pause_sleep', label: '+ Sleep' },
] as const

const THEN_TEXT: Record<Then, string> = {
  pause: 'then pause',
  pause_lock: 'then pause and lock',
  pause_sleep: 'then pause and sleep',
}

function set(payload: { mode: 'minutes' | 'end_of_media'; minutes?: number; then: Then }) {
  haptic('click')
  client.request('timer.set', payload).catch((e: unknown) => {
    useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
  })
}

export function TimerScreen() {
  const timer = useExtras((s) => s.timer)
  const { media } = useMedia()
  const then = useUi((s) => s.timerThen)
  const setThen = useUi((s) => s.setTimerThen)
  const now = useClock(true)

  if (timer === null) return <Skeleton label="Loading the sleep timer" className="h-40" />

  if (timer.active) {
    const left = remainingSeconds(timer.endsAt, now)
    return (
      <Card className="flex flex-col items-center gap-4 py-8 text-center short:gap-3 short:py-5 land:gap-2 land:py-3">
        <MoonStar className="h-8 w-8 text-[var(--color-accent)]" aria-hidden="true" />
        <p className="text-5xl font-semibold tabular-nums land:text-4xl" role="timer">
          {formatCountdown(left)}
        </p>
        <p className="text-[var(--color-text-secondary)]">
          {timer.mode === 'end_of_media' ? 'At the end of this track, ' : ''}
          {timer.then !== null ? THEN_TEXT[timer.then] : ''}. The volume fades over the last 30 seconds.
        </p>
        <Button
          variant="danger"
          size="lg"
          onClick={() => {
            client.request('timer.cancel', {}).catch(() => undefined)
          }}
        >
          Cancel timer
        </Button>
      </Card>
    )
  }

  const session = media === null ? null : currentSession(media)
  const endIn = endOfMediaSeconds(session, now)

  return (
    <div className="flex flex-col gap-3 short:gap-2 land:gap-2">
      <SegmentedControl label="When it ends" options={THEN_OPTIONS} value={then} onChange={setThen} />
      <div className="grid grid-cols-3 gap-3 short:gap-2 land:grid-cols-6 land:gap-2">
        {TIMER_PRESETS.map((m) => (
          <Button key={m} size="lg" className="land:min-h-11" onClick={() => { set({ mode: 'minutes', minutes: m, then }) }}>
            {m} min
          </Button>
        ))}
      </div>
      <Button
        size="lg"
        variant="primary"
        disabled={endIn === null}
        icon={<Clock3 className="h-5 w-5" aria-hidden="true" />}
        onClick={() => {
          set({ mode: 'end_of_media', then })
        }}
      >
        {endIn === null ? 'End of this track (length unknown)' : `End of this track (${formatCountdown(endIn)})`}
      </Button>
    </div>
  )
}
