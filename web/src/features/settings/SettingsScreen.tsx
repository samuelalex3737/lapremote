import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { client, useConnection } from '../../store/remote.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/primitives.tsx'
import { TrackpadSettingsForm } from '../trackpad/TrackpadSettingsPanel.tsx'
import { useTrackpadSettings } from '../trackpad/useTrackpadSettings.ts'

const OS_NAMES = { windows: 'Windows', macos: 'macOS', linux: 'Linux' } as const

export function SettingsScreen() {
  const session = useConnection((s) => s.session)
  const [settings, setSettings] = useTrackpadSettings()
  const [confirmForget, setConfirmForget] = useState(false)
  if (session === null) return null

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Laptop</h2>
        <p className="text-base font-medium">{session.hostName}</p>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {OS_NAMES[session.os]} · You're {session.role === 'owner' ? 'the owner' : 'a guest'}
          {session.features.secureContext ? ' · Secure connection' : ''}
        </p>
      </Card>
      <Card className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Trackpad</h2>
        <TrackpadSettingsForm settings={settings} onChange={setSettings} />
      </Card>
      <Button
        variant="danger"
        size="lg"
        icon={<LogOut className="h-5 w-5" aria-hidden="true" />}
        onClick={() => {
          if (confirmForget) client.forget()
          else setConfirmForget(true)
        }}
      >
        {confirmForget ? 'Tap again to forget this laptop' : 'Forget this laptop on this phone'}
      </Button>
      <p className="text-center text-xs text-[var(--color-text-tertiary)]">LapRemote {__APP_VERSION__}</p>
    </div>
  )
}
