import { Ellipsis, Keyboard, Music2, Rocket, Touchpad, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { haptic } from '../lib/haptics.ts'
import { useUi, type TabId } from '../store/ui.ts'
import { springs } from '../ui/motion.ts'

const ITEMS: { id: TabId; label: string; Icon: LucideIcon }[] = [
  { id: 'now', label: 'Now Playing', Icon: Music2 },
  { id: 'trackpad', label: 'Trackpad', Icon: Touchpad },
  { id: 'keys', label: 'Keys', Icon: Keyboard },
  { id: 'launch', label: 'Launch', Icon: Rocket },
  { id: 'more', label: 'More', Icon: Ellipsis },
]

export function TabBar() {
  const tab = useUi((s) => s.tab)
  const setTab = useUi((s) => s.setTab)
  return (
    <nav
      aria-label="Main"
      className="glass z-20 mx-3 mb-1.5 rounded-[26px] pb-safe md:mx-auto md:w-full md:max-w-2xl land:order-first land:my-2 land:mr-0 land:ml-[max(0.5rem,env(safe-area-inset-left))] land:w-20 land:max-w-none land:pb-0"
    >
      <ul className="flex land:h-full land:flex-col">
        {ITEMS.map(({ id, label, Icon }) => {
          const active = tab === id
          return (
            <li key={id} className="flex-1">
              <button
                type="button"
                aria-current={active ? 'page' : undefined}
                className="relative flex min-h-14 w-full flex-col items-center justify-center gap-1 rounded-[22px] px-0.5 short:min-h-12 land:h-full land:min-h-11 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-accent)]"
                onClick={() => {
                  if (!active) haptic('tick')
                  setTab(id)
                }}
              >
                {active && (
                  <motion.span
                    layoutId="tab-indicator"
                    transition={springs.snappy}
                    className="absolute inset-1 rounded-[20px] bg-[var(--color-surface-strong)]"
                  />
                )}
                <Icon
                  aria-hidden="true"
                  className={`relative h-5 w-5 ${active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-secondary)]'}`}
                  strokeWidth={active ? 2.4 : 2}
                />
                <span
                  className={`relative whitespace-nowrap text-[11px] font-medium leading-none ${active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-secondary)]'}`}
                >
                  {label}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
