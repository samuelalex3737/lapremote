import { Crown, Smartphone, Trash2, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { DeviceInfo } from '../../lib/protocol.ts'
import { RequestError } from '../../lib/ws.ts'
import { client, useConnection } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, Skeleton } from '../../ui/primitives.tsx'

function useDevices(enabled: boolean): DeviceInfo[] | null {
  const [devices, setDevices] = useState<DeviceInfo[] | null>(null)
  useEffect(() => {
    if (!enabled) return
    const off = client.on('devices.state', (p) => {
      setDevices(p.devices)
    })
    client.request('devices.list', {}).catch((e: unknown) => {
      useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'Could not load devices.')
    })
    return off
  }, [enabled])
  return devices
}

export function DevicesScreen() {
  const session = useConnection((s) => s.session)
  const owner = session?.role === 'owner'
  const devices = useDevices(owner)
  const [confirming, setConfirming] = useState<string | null>(null)

  if (session === null) return null
  if (!owner) {
    return (
      <Card>
        <p className="text-[var(--color-text-secondary)]">
          You're a guest on this laptop. The owner can give you full control from their phone.
        </p>
      </Card>
    )
  }
  if (devices === null) return <Skeleton label="Loading devices" className="h-40" />

  const run = (promise: Promise<unknown>) => {
    promise.catch((e: unknown) => {
      useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
    })
  }

  return (
    <ul className="flex flex-col gap-3">
      {devices.map((d) => {
        const self = d.deviceId === session.deviceId
        return (
          <li key={d.deviceId}>
            <Card className="flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-surface-strong)]" aria-hidden="true">
                  {d.role === 'owner' ? <Crown className="h-5 w-5 text-[var(--color-warn)]" /> : <Smartphone className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {d.name}
                    {self && <span className="font-normal text-[var(--color-text-secondary)]"> (this phone)</span>}
                  </p>
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    {d.role === 'owner' ? 'Owner' : 'Guest'} · {d.online ? 'Online' : 'Offline'}
                  </p>
                </div>
              </div>
              {!self && (
                <div className="flex gap-2">
                  <Button
                    className="flex-1"
                    icon={d.role === 'owner' ? <UserRound className="h-4 w-4" aria-hidden="true" /> : <Crown className="h-4 w-4" aria-hidden="true" />}
                    onClick={() => {
                      run(client.request('devices.role', { deviceId: d.deviceId, role: d.role === 'owner' ? 'guest' : 'owner' }))
                    }}
                  >
                    {d.role === 'owner' ? 'Make guest' : 'Make owner'}
                  </Button>
                  <Button
                    className="flex-1"
                    variant="danger"
                    icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
                    onClick={() => {
                      if (confirming === d.deviceId) {
                        setConfirming(null)
                        run(client.request('devices.revoke', { deviceId: d.deviceId }))
                      } else {
                        setConfirming(d.deviceId)
                      }
                    }}
                  >
                    {confirming === d.deviceId ? 'Tap again to remove' : 'Remove'}
                  </Button>
                </div>
              )}
            </Card>
          </li>
        )
      })}
    </ul>
  )
}
