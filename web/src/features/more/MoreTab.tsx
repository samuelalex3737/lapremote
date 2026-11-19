import { Bot, ChevronLeft, ChevronRight, Clapperboard, Power, Settings, Smartphone, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FeatureName } from '../../lib/protocol.ts'
import { useConnection } from '../../store/remote.ts'
import { useUi, type MoreScreen } from '../../store/ui.ts'
import { IconButton } from '../../ui/Button.tsx'
import { ListRow } from '../../ui/primitives.tsx'
import { DevicesScreen } from '../devices/DevicesScreen.tsx'
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
  { id: 'power', title: 'Power', icon: <Power className="h-5 w-5" />, feature: 'power' },
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
    case 'timer':
    case 'power':
    case 'ai':
      // Shows the agent's reason while the laptop doesn't offer this feature.
      return (
        <FeatureGate feature={entry.feature ?? 'scenes'} title={entry.title}>
          {null}
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
      <div className="flex flex-col gap-4 pt-2">
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
          <h1 className="text-2xl font-semibold">{entry.title}</h1>
        </div>
        <Screen entry={entry} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 pt-2">
      <h1 className="text-2xl font-semibold">More</h1>
      <ul className="divide-y divide-[var(--color-line)] overflow-hidden rounded-[var(--radius-card)] bg-[var(--color-surface)] ring-1 ring-inset ring-[var(--color-line)]">
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
