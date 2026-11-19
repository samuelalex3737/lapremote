import { client, useConnection } from '../../store/remote.ts'
import { FeatureGate } from '../FeatureGate.tsx'
import { Trackpad } from './Trackpad.tsx'

export function TrackpadTab() {
  const session = useConnection((s) => s.session)
  if (session === null) return null
  return (
    <div className="flex min-h-0 flex-1 flex-col pt-2">
      <FeatureGate feature="input" title="The trackpad">
        <Trackpad client={client} session={session} />
      </FeatureGate>
    </div>
  )
}
