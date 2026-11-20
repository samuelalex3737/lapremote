import { Pencil } from 'lucide-react'
import { BUTTON_ICONS } from '../../lib/buttonIcons.ts'
import { haptic } from '../../lib/haptics.ts'
import { buttonMessage, matchLayout } from '../../lib/layouts.ts'
import type { Layout } from '../../lib/protocol.ts'
import { client, useLaptopContext, useLayouts } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { IconButton } from '../../ui/Button.tsx'
import { EmptyState, Skeleton } from '../../ui/primitives.tsx'

function run(layout: Layout, index: number) {
  const button = layout.buttons[index]
  if (button === undefined) return
  const message = buttonMessage(button.action)
  haptic('click')
  client.send(message.type, message.payload)
}

/** The buttons of the layout that fits the app in front (or the one picked). */
export function LayoutPad() {
  const layouts = useLayouts((s) => s.layouts)
  const context = useLaptopContext((s) => s.context)
  const picked = useUi((s) => s.layoutPick)
  const pick = useUi((s) => s.setLayoutPick)
  const setTab = useUi((s) => s.setTab)
  const setMore = useUi((s) => s.setMore)

  if (layouts === null) return <Skeleton label="Loading layouts" className="h-48 w-full" />
  const matched = matchLayout(layouts, context)
  const current = layouts.find((l) => l.id === picked) ?? matched ?? layouts[0] ?? null
  if (current === null) {
    return <EmptyState icon={<Pencil className="h-9 w-9" />} title="No layouts yet" body="Make one in More > Layouts." />
  }
  const edit = () => {
    setMore('layouts')
    setTab('more')
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <div className="flex items-center gap-1">
      <div className="-ml-4 flex min-w-0 flex-1 gap-2 overflow-x-auto pl-4 pb-0.5" data-no-swipe role="tablist" aria-label="Layouts">
        {layouts.map((l) => {
          const active = l.id === current.id
          return (
            <button
              key={l.id}
              type="button"
              role="tab"
              aria-selected={active}
              className={`min-h-11 shrink-0 rounded-full px-4 text-sm font-medium ring-1 ring-inset ${
                active
                  ? 'bg-[var(--color-text)] text-[var(--color-bg)] ring-transparent'
                  : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] ring-[var(--color-line)]'
              }`}
              onClick={() => {
                // Picking the one that fits anyway goes back to following the laptop.
                pick(l.id === matched?.id ? null : l.id)
              }}
            >
              {l.name}
              {l.id === matched?.id && <span className="sr-only"> (in front)</span>}
            </button>
          )
        })}
      </div>
        <IconButton label="Edit layouts" variant="plain" onClick={edit}>
          <Pencil className="h-5 w-5" />
        </IconButton>
      </div>
      <div className="grid grid-cols-3 gap-2 land:grid-cols-4" aria-label={`${current.name} buttons`} role="group">
        {current.buttons.map((b, i) => {
          const Icon = b.icon != null ? BUTTON_ICONS[b.icon] : undefined
          const danger = b.icon === 'phone-off'
          return (
            <button
              key={`${b.label}-${String(i)}`}
              type="button"
              className={`flex min-h-20 flex-col items-center justify-center gap-1.5 rounded-[var(--radius-control)] px-2 py-2 text-center text-sm font-medium ring-1 ring-inset outline-none active:scale-[0.97] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] short:min-h-16 land:min-h-14 ${
                danger
                  ? 'bg-[var(--color-danger)]/12 text-[var(--color-danger)] ring-[var(--color-danger)]/30'
                  : 'bg-[var(--color-surface-strong)] ring-[var(--color-line)]'
              }`}
              onClick={() => {
                run(current, i)
              }}
            >
              {Icon !== undefined && <Icon className="h-6 w-6" aria-hidden="true" />}
              <span className="line-clamp-2 leading-tight">{b.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
