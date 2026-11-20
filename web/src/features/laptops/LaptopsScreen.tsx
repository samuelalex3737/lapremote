import { Laptop, Power } from 'lucide-react'
import { RequestError } from '../../lib/ws.ts'
import { client, useConnection, usePeers, type Peer } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, EmptyState, Skeleton } from '../../ui/primitives.tsx'

function ago(ms: number | null): string {
  if (ms === null) return ''
  const minutes = Math.round((Date.now() - ms) / 60_000)
  if (minutes < 1) return 'seen just now'
  if (minutes < 60) return `seen ${String(minutes)} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `seen ${String(hours)} h ago`
  return `seen ${String(Math.round(hours / 24))} days ago`
}

function wake(peer: Peer) {
  if (peer.mac === null) return
  client.request('wol.wake', { mac: peer.mac }).then(
    () => {
      useUi.getState().showToast('success', `Wake signal sent to ${peer.name}. It can take a minute.`)
    },
    (e: unknown) => {
      useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
    },
  )
}

/** Other LapRemote laptops on this network: switch to one, or wake one that's asleep. */
export function LaptopsScreen() {
  const peers = usePeers((s) => s.peers)
  const session = useConnection((s) => s.session)
  if (session === null) return null
  if (session.role !== 'owner') {
    return (
      <Card>
        <p className="text-[var(--color-text-secondary)]">Only the owner can see the other laptops.</p>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-3 short:gap-2 land:grid land:grid-cols-2 land:items-start land:gap-2">
      <div className="flex flex-col gap-2">
        <Card className="flex items-center gap-3 p-3">
          <Laptop className="h-6 w-6 shrink-0 text-[var(--color-accent)]" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{session.hostName}</p>
            <p className="text-sm text-[var(--color-success)]">Connected now</p>
          </div>
        </Card>
        <p className="text-xs text-[var(--color-text-tertiary)]">
          Each laptop pairs with this phone once, with its own code. Waking needs Wake-on-LAN turned on in that laptop's
          settings, and many laptops only wake over a network cable.
        </p>
      </div>
      {peers === null ? (
        <Skeleton label="Looking for other laptops" className="h-20 w-full" />
      ) : peers.length === 0 ? (
        <EmptyState
          icon={<Laptop className="h-9 w-9" />}
          title="No other laptops yet"
          body="Start LapRemote on another laptop on this Wi-Fi and it shows up here."
        />
      ) : (
        <ul className="flex flex-col gap-2 land:grid land:grid-cols-2" aria-label="Other laptops">
          {peers.map((peer) => (
            <li key={peer.peerId}>
              <Card className="flex items-center gap-3 p-3">
                <span
                  aria-hidden="true"
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${peer.online ? 'bg-[var(--color-success)]' : 'bg-[var(--color-text-tertiary)]'}`}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{peer.name}</p>
                  <p className="text-sm text-[var(--color-text-secondary)]">{peer.online ? 'Online' : `Asleep or off, ${ago(peer.lastSeenAt)}`}</p>
                </div>
                {peer.online ? (
                  <Button
                    variant="primary"
                    onClick={() => {
                      window.location.assign(peer.url)
                    }}
                  >
                    Open
                  </Button>
                ) : peer.mac !== null ? (
                  <Button
                    icon={<Power className="h-4 w-4" aria-hidden="true" />}
                    onClick={() => {
                      wake(peer)
                    }}
                  >
                    Wake
                  </Button>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
