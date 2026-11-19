import { useEffect, useState } from 'react'
import { useMedia } from '../../app/client.ts'
import { formatTime, positionAt } from '../../lib/media.ts'
import type { MediaStore } from '../../lib/mediaStore.ts'
import type { MediaSession } from '../../lib/protocol.ts'
import type { RemoteClient } from '../../lib/ws.ts'

interface Props {
  client: RemoteClient
  store: MediaStore
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => {
      setNow(Date.now())
    }, 500)
    return () => {
      clearInterval(timer)
    }
  }, [active])
  return now
}

function SessionCard(props: {
  client: RemoteClient
  session: MediaSession
  now: number
  image: string | null
}) {
  const { client, session, now, image } = props
  const position = positionAt(session, now)
  const send = (type: 'media.prev' | 'media.toggle' | 'media.next') => {
    client.send(type, { sessionId: session.id })
  }
  const seek = (by: number) => {
    client.send('media.seek', { sessionId: session.id, by })
  }
  const button =
    'min-h-12 min-w-12 flex-1 rounded-2xl border border-white/10 bg-white/[0.06] text-sm font-medium active:bg-white/15'

  return (
    <li className="flex flex-col gap-3 rounded-3xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center gap-3">
        {image !== null ? (
          <img src={image} alt="" className="h-16 w-16 shrink-0 rounded-xl object-cover" />
        ) : (
          <div className="h-16 w-16 shrink-0 rounded-xl bg-white/10" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{session.title || 'Unknown title'}</p>
          <p className="truncate text-sm text-zinc-400">
            {session.artist || session.appName} · {session.appName}
          </p>
          <p className="text-xs tabular-nums text-zinc-400">
            {session.status === 'playing' ? 'Playing' : session.status === 'paused' ? 'Paused' : 'Stopped'}
            {' · '}
            {formatTime(position)} / {formatTime(session.duration)}
          </p>
        </div>
      </div>
      <div className="flex gap-2">
        <button type="button" aria-label="Previous" className={button} disabled={!session.canPrev} onClick={() => { send('media.prev') }}>
          Prev
        </button>
        <button type="button" aria-label="Back 10 seconds" className={button} onClick={() => { seek(-10) }}>
          -10s
        </button>
        <button type="button" aria-label={session.status === 'playing' ? 'Pause' : 'Play'} className={button} onClick={() => { send('media.toggle') }}>
          {session.status === 'playing' ? 'Pause' : 'Play'}
        </button>
        <button type="button" aria-label="Forward 10 seconds" className={button} onClick={() => { seek(10) }}>
          +10s
        </button>
        <button type="button" aria-label="Next" className={button} disabled={!session.canNext} onClick={() => { send('media.next') }}>
          Next
        </button>
      </div>
    </li>
  )
}

/** Every media session on the laptop with basic controls, plus the system volume. */
export function MediaPanel({ client, store }: Props) {
  const { media: view, volume } = useMedia()
  const playing = view?.sessions.some((s) => s.status === 'playing') ?? false
  const now = useNow(playing)

  if (view === null) {
    return <div className="h-40 animate-pulse rounded-3xl bg-white/5" aria-label="Loading media" />
  }

  return (
    <div className="flex flex-col gap-4">
      {view.sessions.length === 0 ? (
        <p className="rounded-3xl border border-white/10 bg-white/5 p-6 text-center text-zinc-300">
          Nothing playing
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {view.sessions.map((s) => (
            <SessionCard
              key={s.id}
              client={client}
              session={s}
              now={now}
              image={store.artwork.get(s.artworkId)}
            />
          ))}
        </ul>
      )}
      {volume !== null && (
        <label className="flex flex-col gap-2 rounded-3xl border border-white/10 bg-white/5 p-4">
          <span className="flex justify-between text-sm">
            <span className="font-medium">Volume</span>
            <span className="tabular-nums text-zinc-400">
              {volume.muted ? 'Muted' : `${String(volume.level)}%`}
            </span>
          </span>
          <input
            type="range"
            min={0}
            max={100}
            value={volume.level}
            onChange={(e) => {
              store.setVolumeLocally(Number(e.target.value))
            }}
            className="h-11 w-full accent-white"
          />
          <button
            type="button"
            className="min-h-11 rounded-2xl border border-white/10 text-sm font-medium"
            onClick={() => {
              client.send('volume.mute', { muted: !volume.muted })
            }}
          >
            {volume.muted ? 'Unmute' : 'Mute'}
          </button>
        </label>
      )}
    </div>
  )
}
