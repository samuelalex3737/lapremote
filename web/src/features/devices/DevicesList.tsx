import { useEffect, useState } from 'react'
import type { DeviceInfo } from '../../lib/protocol.ts'
import { RequestError, type RemoteClient } from '../../lib/ws.ts'

interface Props {
  client: RemoteClient
  selfId: string
}

export function DevicesList({ client, selfId }: Props) {
  const [devices, setDevices] = useState<DeviceInfo[] | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const off = client.on('devices.state', (payload) => {
      setDevices(payload.devices)
    })
    client.request('devices.list', {}).catch((e: unknown) => {
      setError(e instanceof RequestError ? e.message : 'Could not load devices.')
    })
    return off
  }, [client])

  const run = (promise: Promise<unknown>) => {
    setError(null)
    promise.catch((e: unknown) => {
      setError(e instanceof RequestError ? e.message : 'That did not work.')
    })
  }

  if (devices === null) {
    return <div className="h-24 animate-pulse rounded-3xl bg-white/5" aria-label="Loading devices" />
  }

  return (
    <section className="flex flex-col gap-3 text-left" aria-labelledby="devices-title">
      <h2 id="devices-title" className="text-lg font-semibold">
        Paired devices
      </h2>
      <ul className="flex flex-col divide-y divide-white/10 rounded-3xl border border-white/10 bg-white/5">
        {devices.map((device) => {
          const isSelf = device.deviceId === selfId
          return (
            <li key={device.deviceId} className="flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    {device.name}
                    {isSelf && <span className="text-zinc-400"> (this phone)</span>}
                  </p>
                  <p className="text-sm text-zinc-400">
                    {device.role === 'owner' ? 'Owner' : 'Guest'}
                    {' · '}
                    {device.online ? 'Online' : 'Offline'}
                  </p>
                </div>
              </div>
              {!isSelf && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="min-h-11 flex-1 rounded-full border border-white/15 px-4 text-sm font-medium active:scale-95"
                    onClick={() => {
                      run(
                        client.request('devices.role', {
                          deviceId: device.deviceId,
                          role: device.role === 'owner' ? 'guest' : 'owner',
                        }),
                      )
                    }}
                  >
                    {device.role === 'owner' ? 'Make guest' : 'Make owner'}
                  </button>
                  <button
                    type="button"
                    className="min-h-11 flex-1 rounded-full border border-rose-400/40 px-4 text-sm font-medium text-rose-200 active:scale-95"
                    onClick={() => {
                      if (confirming === device.deviceId) {
                        setConfirming(null)
                        run(client.request('devices.revoke', { deviceId: device.deviceId }))
                      } else {
                        setConfirming(device.deviceId)
                      }
                    }}
                  >
                    {confirming === device.deviceId ? 'Tap again to remove' : 'Remove'}
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {error !== null && (
        <p role="alert" className="text-sm text-rose-300">
          {error}
        </p>
      )}
    </section>
  )
}
