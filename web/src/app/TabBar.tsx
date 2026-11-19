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
    <nav aria-label="Main" className="glass z-20 mx-3 mb-2 rounded-[28px] pb-safe">
      <ul className="flex">
        {ITEMS.map(({ id, label, Icon }) => {
          const active = tab === id
          return (
            <li key={id} className="flex-1">
              <button
                type="button"
                aria-current={active ? 'page' : undefined}
                className="relative flex min-h-16 w-full flex-col items-center justify-center gap-1 rounded-[22px] px-1 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-accent)]"
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
                  className={`relative h-6 w-6 ${active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-secondary)]'}`}
                  strokeWidth={active ? 2.4 : 2}
                />
                <span
                  className={`relative text-[11px] font-medium leading-none ${active ? 'text-[var(--color-text)]' : 'text-[var(--color-text-secondary)]'}`}
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
