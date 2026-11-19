import { useState } from 'react'
import { client, useConnection } from '../../store/remote.ts'
import { Card, SegmentedControl } from '../../ui/primitives.tsx'
import { FeatureGate } from '../FeatureGate.tsx'
import { ScreenPreview } from '../preview/ScreenPreview.tsx'
import { AirMouse } from './AirMouse.tsx'
import { Trackpad } from './Trackpad.tsx'
import { useTrackpadSettings } from './useTrackpadSettings.ts'

type Surface = 'trackpad' | 'screen' | 'air'

const SURFACES: readonly { value: Surface; label: string }[] = [
  { value: 'trackpad', label: 'Trackpad' },
  { value: 'screen', label: 'Screen' },
]
const WITH_AIR: readonly { value: Surface; label: string }[] = [...SURFACES, { value: 'air', label: 'Air mouse' }]

export function TrackpadTab() {
  const session = useConnection((s) => s.session)
  const [settings] = useTrackpadSettings()
  const [picked, setSurface] = useState<Surface>('trackpad')
  const surface = picked === 'air' && !settings.airMouse ? 'trackpad' : picked
  if (session === null) return null
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 pt-2">
      <SegmentedControl label="Surface" options={settings.airMouse ? WITH_AIR : SURFACES} value={surface} onChange={setSurface} />
      {surface === 'air' ? (
        <FeatureGate feature="input" title="The air mouse">
          <AirMouse client={client} session={session} />
        </FeatureGate>
      ) : surface === 'trackpad' ? (
        <FeatureGate feature="input" title="The trackpad">
          <Trackpad client={client} session={session} />
        </FeatureGate>
      ) : session.role !== 'owner' ? (
        <Card>
          <p className="text-[var(--color-text-secondary)]">Only the owner can see and click the laptop screen.</p>
        </Card>
      ) : (
        <FeatureGate feature="preview" title="Screen preview">
          <ScreenPreview client={client} />
        </FeatureGate>
      )}
    </div>
  )
}
