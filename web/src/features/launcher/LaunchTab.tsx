import { FeatureGate } from '../FeatureGate.tsx'

export function LaunchTab() {
  return (
    <div className="flex flex-col gap-4 pt-2">
      <h1 className="text-2xl font-semibold">Launch</h1>
      <FeatureGate feature="launcher" title="Launching apps and sites">
        <p className="text-[var(--color-text-secondary)]">Your shortcuts will appear here.</p>
      </FeatureGate>
    </div>
  )
}
