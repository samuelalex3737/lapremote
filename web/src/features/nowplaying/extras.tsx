import { MoonStar } from 'lucide-react'
import { useClock } from '../../app/useClock.ts'
import { visibleShortcuts } from '../../lib/shortcuts.ts'
import { formatCountdown, remainingSeconds } from '../../lib/timer.ts'
import { useConnection, useExtras } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { launch } from '../launcher/launch.ts'
import { ShortcutIcon } from '../launcher/shortcutIcon.tsx'

/** Live sleep-timer countdown; tap to open the timer. */
export function TimerPill() {
  const timer = useExtras((s) => s.timer)
  const active = timer?.active === true
  const now = useClock(active)
  if (!active) return null
  return (
    <button
      type="button"
      className="mx-auto inline-flex min-h-11 items-center gap-2 rounded-full bg-[var(--color-accent)]/15 px-4 text-sm font-medium text-[var(--color-accent)] ring-1 ring-inset ring-[var(--color-accent)]/30"
      onClick={() => {
        useUi.getState().setTab('more')
        useUi.getState().setMore('timer')
      }}
    >
      <MoonStar className="h-4 w-4" aria-hidden="true" />
      Sleep timer <span className="tabular-nums">{formatCountdown(remainingSeconds(timer.endsAt, now))}</span>
    </button>
  )
}

/** The first few launcher shortcuts, shown when nothing is playing. */
export function QuickLaunch() {
  const shortcuts = visibleShortcuts(useExtras((s) => s.shortcuts)).slice(0, 4)
  const owner = useConnection((s) => s.session?.role === 'owner')
  const launcher = useConnection((s) => s.session?.features.launcher.available === true)
  if (!owner || !launcher || shortcuts.length === 0) return null
  return (
    <div className="mt-2 grid w-full grid-cols-4 gap-2">
      {shortcuts.map((s) => (
        <button
          key={s.id}
          type="button"
          aria-label={`Open ${s.name}`}
          className="flex min-h-11 flex-col items-center gap-1 rounded-2xl p-1 outline-none active:scale-95 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          onClick={() => {
            launch(s)
          }}
        >
          <ShortcutIcon shortcut={s} />
          <span className="w-full truncate text-center text-xs text-[var(--color-text-secondary)]">{s.name}</span>
        </button>
      ))}
    </div>
  )
}
