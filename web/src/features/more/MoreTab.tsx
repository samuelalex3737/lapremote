import { Bot, ChevronLeft, Clapperboard, LayoutGrid, Laptop, Power, Send, Settings, Smartphone, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FeatureName } from '../../lib/protocol.ts'
import { useConnection } from '../../store/remote.ts'
import { useUi, type MoreScreen } from '../../store/ui.ts'
import { IconButton } from '../../ui/Button.tsx'
import { AiScreen } from '../ai/AiScreen.tsx'
import { DevicesScreen } from '../devices/DevicesScreen.tsx'
import { LaptopsScreen } from '../laptops/LaptopsScreen.tsx'
import { LayoutsScreen } from '../layouts/LayoutsScreen.tsx'
import { SendScreen } from '../send/SendScreen.tsx'
import { PowerScreen } from '../power/PowerScreen.tsx'
import { ScenesScreen } from '../scenes/ScenesScreen.tsx'
import { TimerScreen } from '../timer/TimerScreen.tsx'
import { FeatureGate } from '../FeatureGate.tsx'
import { SettingsScreen } from '../settings/SettingsScreen.tsx'

interface Entry {
  id: Exclude<MoreScreen, 'menu'>
  title: string
  icon: ReactNode
  feature?: FeatureName
}

const ENTRIES: Entry[] = [
  { id: 'scenes', title: 'Scenes', icon: <Clapperboard className="h-5 w-5" />, feature: 'scenes' },
  { id: 'timer', title: 'Sleep timer', icon: <Timer className="h-5 w-5" />, feature: 'timer' },
  { id: 'power', title: 'Power & display', icon: <Power className="h-5 w-5" />, feature: 'power' },
  { id: 'ai', title: 'Ask LapRemote', icon: <Bot className="h-5 w-5" />, feature: 'ai' },
  { id: 'send', title: 'Send to laptop', icon: <Send className="h-5 w-5" /> },
  { id: 'layouts', title: 'Layouts', icon: <LayoutGrid className="h-5 w-5" /> },
  { id: 'laptops', title: 'Laptops', icon: <Laptop className="h-5 w-5" /> },
  { id: 'devices', title: 'Devices', icon: <Smartphone className="h-5 w-5" /> },
  { id: 'settings', title: 'Settings', icon: <Settings className="h-5 w-5" /> },
]

function Screen({ entry }: { entry: Entry }) {
  switch (entry.id) {
    case 'devices':
      return <DevicesScreen />
    case 'settings':
      return <SettingsScreen />
    case 'scenes':
      return (
        <FeatureGate feature="scenes" title="Scenes">
          <ScenesScreen />
        </FeatureGate>
      )
    case 'timer':
      return (
        <FeatureGate feature="timer" title="The sleep timer">
          <TimerScreen />
        </FeatureGate>
      )
    case 'power':
      return <PowerScreen />
    case 'ai':
      return (
        <FeatureGate feature="ai" title="The AI assistant">
          <AiScreen />
        </FeatureGate>
      )
    case 'send':
      return <SendScreen />
    case 'layouts':
      return <LayoutsScreen />
    case 'laptops':
      return <LaptopsScreen />
  }
}

export function MoreTab() {
  const screen = useUi((s) => s.more)
  const setScreen = useUi((s) => s.setMore)
  const features = useConnection((s) => s.session?.features)
  const entry = ENTRIES.find((e) => e.id === screen)

  if (entry !== undefined) {
    return (
      <div className="flex flex-col gap-3 pt-1 short:gap-2 land:gap-2">
        <div className="flex items-center gap-2">
          <IconButton
            label="Back"
            variant="plain"
            onClick={() => {
              setScreen('menu')
            }}
          >
            <ChevronLeft className="h-6 w-6" />
          </IconButton>
          <h1 className="text-xl font-semibold">{entry.title}</h1>
        </div>
        <Screen entry={entry} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 pt-1">
      <h1 className="text-xl font-semibold">More</h1>
      <ul className="grid grid-cols-3 gap-2.5 short:gap-2 land:grid-cols-5 land:gap-2">
        {ENTRIES.map((e) => {
          const status = e.feature !== undefined ? features?.[e.feature] : undefined
          const unavailable = status !== undefined && !status.available
          return (
            <li key={e.id}>
              <button
                type="button"
                className="flex min-h-24 w-full flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] bg-[var(--color-surface)] px-2 py-3 text-center ring-1 ring-inset ring-[var(--color-line)] outline-none active:scale-[0.97] active:bg-[var(--color-surface-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] short:min-h-[5.25rem] land:min-h-20"
                onClick={() => {
                  setScreen(e.id)
                }}
              >
                <span className="text-[var(--color-text-secondary)]" aria-hidden="true">
                  {e.icon}
                </span>
                <span className="text-sm leading-tight font-medium">{e.title}</span>
                {unavailable && <span className="text-[11px] leading-none text-[var(--color-text-tertiary)]">Not available yet</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
