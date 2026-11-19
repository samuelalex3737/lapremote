import { ShieldCheck } from 'lucide-react'
import { Card } from '../../ui/primitives.tsx'

/**
 * Explains why a feature is missing on plain http and how to turn on HTTPS.
 * Browsers only allow the microphone and motion sensors on secure pages.
 */
export function NeedsHttps({ feature }: { feature: string }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-[var(--color-accent)]" aria-hidden="true" />
        <h2 className="text-base font-semibold">{feature} needs HTTPS</h2>
      </div>
      <p className="text-sm text-[var(--color-text-secondary)]">
        Your phone only allows this on a secure connection. Two free ways to get one:
      </p>
      <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm text-[var(--color-text-secondary)]">
        <li>
          <span className="font-medium text-[var(--color-text)]">Tailscale.</span> Install it on the laptop and phone, run{' '}
          <code className="rounded bg-[var(--color-bg-raised)] px-1">tailscale serve 7777</code> on the laptop, then open the
          https address it prints.
        </li>
        <li>
          <span className="font-medium text-[var(--color-text)]">mkcert.</span> Make a certificate for the laptop, add it to{' '}
          <code className="rounded bg-[var(--color-bg-raised)] px-1">config.json</code> and start LapRemote with{' '}
          <code className="rounded bg-[var(--color-bg-raised)] px-1">--https</code>.
        </li>
      </ol>
      <p className="text-sm text-[var(--color-text-secondary)]">Step-by-step help is in docs/HTTPS.md on the laptop.</p>
    </Card>
  )
}
