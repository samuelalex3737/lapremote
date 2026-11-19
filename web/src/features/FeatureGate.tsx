import { Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FeatureName } from '../lib/protocol.ts'
import { useConnection } from '../store/remote.ts'
import { EmptyState } from '../ui/primitives.tsx'

/**
 * Renders children only when the agent reports the feature as available; otherwise
 * shows the agent's own reason (from auth.ok.features), so nothing is faked.
 */
export function FeatureGate({ feature, title, children }: { feature: FeatureName; title: string; children: ReactNode }) {
  const status = useConnection((s) => s.session?.features[feature])
  if (status === undefined) return null
  if (!status.available) {
    return (
      <EmptyState
        icon={<Lock className="h-9 w-9" />}
        title={`${title} isn't available`}
        body={status.reason ?? 'Your laptop does not support this.'}
      />
    )
  }
  return <>{children}</>
}
