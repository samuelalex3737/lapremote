import { Bot, ChevronLeft, ChevronRight, Clapperboard, Power, Settings, Smartphone, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FeatureName } from '../../lib/protocol.ts'
import { useConnection } from '../../store/remote.ts'
import { useUi, type MoreScreen } from '../../store/ui.ts'
import { IconButton } from '../../ui/Button.tsx'
import { ListRow } from '../../ui/primitives.tsx'
import { AiScreen } from '../ai/AiScreen.tsx'
import { DevicesScreen } from '../devices/DevicesScreen.tsx'
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
      <ul className="divide-y divide-[var(--color-line)] overflow-hidden rounded-[var(--radius-card)] bg-[var(--color-surface)] ring-1 ring-inset ring-[var(--color-line)] land:grid land:grid-cols-2 land:divide-y-0">
        {ENTRIES.map((e) => {
          const status = e.feature !== undefined ? features?.[e.feature] : undefined
          const unavailable = status !== undefined && !status.available
          return (
            <li key={e.id}>
              <ListRow
                icon={e.icon}
                title={e.title}
                {...(unavailable ? { subtitle: 'Not available yet' } : {})}
                trailing={<ChevronRight className="h-5 w-5 text-[var(--color-text-tertiary)]" aria-hidden="true" />}
                onClick={() => {
                  setScreen(e.id)
                }}
              />
            </li>
          )
        })}
      </ul>
    </div>
  )
}
