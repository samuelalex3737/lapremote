import { useState } from 'react'
import { client, useConnection } from '../../store/remote.ts'
import { Card, SegmentedControl } from '../../ui/primitives.tsx'
import { FeatureGate } from '../FeatureGate.tsx'
import { ScreenPreview } from '../preview/ScreenPreview.tsx'
import { Trackpad } from './Trackpad.tsx'

type Surface = 'trackpad' | 'screen'

const SURFACES = [
  { value: 'trackpad', label: 'Trackpad' },
  { value: 'screen', label: 'Screen' },
] as const

export function TrackpadTab() {
  const session = useConnection((s) => s.session)
  const [surface, setSurface] = useState<Surface>('trackpad')
  if (session === null) return null
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 pt-2">
      <SegmentedControl label="Surface" options={SURFACES} value={surface} onChange={setSurface} />
      {surface === 'trackpad' ? (
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
