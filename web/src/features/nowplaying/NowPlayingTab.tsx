import { Music2, Pause, Play, RotateCcw, RotateCw, SkipBack, SkipForward, Volume2, VolumeX } from 'lucide-react'
import { useEffect, useState } from 'react'
import { currentSession, formatTime, positionAt } from '../../lib/media.ts'
import type { MediaSession } from '../../lib/protocol.ts'
import { client, mediaStore, useMedia } from '../../store/remote.ts'
import { IconButton } from '../../ui/Button.tsx'
import { Card, EmptyState, Skeleton } from '../../ui/primitives.tsx'
import { Slider } from '../../ui/Slider.tsx'

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

function SessionChips({ sessions, currentId }: { sessions: MediaSession[]; currentId: string | null }) {
  if (sessions.length < 2) return null
  return (
    <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" data-no-swipe role="tablist" aria-label="Players">
      {sessions.map((s) => {
        const active = s.id === currentId
        return (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`min-h-11 shrink-0 rounded-full px-4 text-sm font-medium ring-1 ring-inset ${
              active
                ? 'bg-[var(--color-text)] text-[var(--color-bg)] ring-transparent'
                : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] ring-[var(--color-line)]'
            }`}
            onClick={() => {
              client.send('media.select', { sessionId: s.id })
            }}
          >
            {s.appName}
            {s.status === 'playing' && ' ·'}
          </button>
        )
      })}
    </div>
  )
}

export function NowPlayingTab() {
  const { media, volume } = useMedia()
  const session = media === null ? null : currentSession(media)
  const now = useNow(session?.status === 'playing')

  if (media === null) {
    return (
      <div className="flex flex-col gap-4 pt-2">
        <Skeleton label="Loading what's playing" className="aspect-square w-full" />
        <Skeleton label="Loading controls" className="h-24 w-full" />
      </div>
    )
  }

  const image = session !== null ? mediaStore.artwork.get(session.artworkId) : null
  const position = session !== null ? positionAt(session, now) : null
  const playing = session?.status === 'playing'
  const target = session !== null ? { sessionId: session.id } : {}

  return (
    <div className="flex flex-col gap-5 pt-2">
      <SessionChips sessions={media.sessions} currentId={session?.id ?? null} />

      {session === null ? (
        <EmptyState icon={<Music2 className="h-10 w-10" />} title="Nothing playing" body="Start something on your laptop and it shows up here." />
      ) : (
        <>
          <div className="mx-auto aspect-square w-full max-w-[340px] overflow-hidden rounded-[28px] bg-[var(--color-surface-strong)] shadow-[var(--shadow-soft)]">
            {image !== null ? (
              <img src={image} alt={`Artwork for ${session.title}`} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-[var(--color-text-tertiary)]">
                <Music2 className="h-16 w-16" aria-hidden="true" />
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
              {session.appName}
            </p>
            <h1 className="truncate text-2xl font-semibold">{session.title || 'Unknown title'}</h1>
            <p className="truncate text-base text-[var(--color-text-secondary)]">{session.artist}</p>
            <p className="pt-1 text-sm tabular-nums text-[var(--color-text-secondary)]">
              {formatTime(position)} / {formatTime(session.duration)}
            </p>
          </div>
          <div className="flex items-center justify-between">
            <IconButton label="Previous" size="lg" variant="plain" disabled={!session.canPrev} onClick={() => { client.send('media.prev', target) }}>
              <SkipBack className="h-7 w-7" />
            </IconButton>
            <IconButton label="Back 10 seconds" size="lg" variant="plain" onClick={() => { client.send('media.seek', { ...target, by: -10 }) }}>
              <RotateCcw className="h-7 w-7" />
            </IconButton>
            <IconButton label={playing ? 'Pause' : 'Play'} size="xl" variant="solid" onClick={() => { client.send('media.toggle', target) }}>
              {playing ? <Pause className="h-9 w-9" fill="currentColor" /> : <Play className="ml-1 h-9 w-9" fill="currentColor" />}
            </IconButton>
            <IconButton label="Forward 10 seconds" size="lg" variant="plain" onClick={() => { client.send('media.seek', { ...target, by: 10 }) }}>
              <RotateCw className="h-7 w-7" />
            </IconButton>
            <IconButton label="Next" size="lg" variant="plain" disabled={!session.canNext} onClick={() => { client.send('media.next', target) }}>
              <SkipForward className="h-7 w-7" />
            </IconButton>
          </div>
        </>
      )}

      {volume !== null && (
        <Card className="flex items-center gap-3">
          <IconButton
            label={volume.muted ? 'Unmute' : 'Mute'}
            onClick={() => {
              client.send('volume.mute', { muted: !volume.muted })
            }}
          >
            {volume.muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
          </IconButton>
          <Slider
            label="Volume"
            hideLabel
            value={volume.level}
            valueText={volume.muted ? 'Muted' : `${String(volume.level)}%`}
            onChange={(level) => {
              mediaStore.setVolumeLocally(level)
            }}
          />
          <span className="w-12 shrink-0 text-right text-sm tabular-nums text-[var(--color-text-secondary)]">
            {volume.muted ? 'Muted' : `${String(volume.level)}%`}
          </span>
        </Card>
      )}
    </div>
  )
}
