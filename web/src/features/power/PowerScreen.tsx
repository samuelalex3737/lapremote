import { Lock, Moon, Power, RotateCcw, Sun } from 'lucide-react'
import type { PowerActionName } from '../../lib/protocol.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, useConnection, useExtras } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { HoldButton } from '../../ui/HoldButton.tsx'
import { Card } from '../../ui/primitives.tsx'
import { Slider } from '../../ui/Slider.tsx'
import { FeatureGate } from '../FeatureGate.tsx'

const ACTIONS: { action: PowerActionName; label: string; icon: React.ReactNode }[] = [
  { action: 'lock', label: 'Lock', icon: <Lock className="h-6 w-6" /> },
  { action: 'sleep', label: 'Sleep', icon: <Moon className="h-6 w-6" /> },
  { action: 'restart', label: 'Restart', icon: <RotateCcw className="h-6 w-6" /> },
  { action: 'shutdown', label: 'Shut down', icon: <Power className="h-6 w-6" /> },
]

/** Hold-to-confirm on the phone, then a single-use token from the laptop. */
async function runPower(action: PowerActionName): Promise<void> {
  const reply = await client.request('power.prepare', { action })
  if (reply.type !== 'power.token') throw new RequestError('Your laptop did not confirm.')
  await client.request('power.action', { action, confirmToken: reply.payload.confirmToken })
}

function Brightness() {
  const brightness = useExtras((s) => s.brightness)
  if (brightness === null || !brightness.supported || brightness.level === null) return null
  const level = brightness.level
  return (
    <Card>
      <Slider
        label="Screen brightness"
        icon={<Sun className="h-4 w-4" aria-hidden="true" />}
        value={level}
        valueText={`${String(level)}%`}
        onChange={(next) => {
          useExtras.setState({ brightness: { ...brightness, level: next } })
          client.send('brightness.set', { level: next })
        }}
      />
    </Card>
  )
}

export function PowerScreen() {
  const owner = useConnection((s) => s.session?.role === 'owner')
  if (!owner) {
    return (
      <Card>
        <p className="text-[var(--color-text-secondary)]">Only the owner can lock or turn off this laptop.</p>
      </Card>
    )
  }
  return (
    <div className="flex flex-col gap-3 short:gap-2 land:grid land:grid-cols-3 land:gap-2">
      <div className="land:row-span-2 land:flex land:flex-col land:[&>*]:flex-1">
        <Brightness />
      </div>
      <FeatureGate feature="power" title="Power controls">
        {ACTIONS.map((a) => (
          <HoldButton
            key={a.action}
            label={a.label}
            icon={a.icon}
            tone={a.action === 'lock' ? 'accent' : 'danger'}
            onConfirm={() => {
              runPower(a.action).then(
                () => {
                  useUi.getState().showToast('success', `${a.label}: done`)
                },
                (e: unknown) => {
                  useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
                },
              )
            }}
          />
        ))}
      </FeatureGate>
    </div>
  )
}
