import {
  Captions,
  Expand,
  Monitor,
  Music2,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { movieKeys, type Mode } from '../../lib/adaptive.ts'
import { currentSession, positionAt } from '../../lib/media.ts'
import type { KeyName, MediaSession } from '../../lib/protocol.ts'
import { client, mediaStore, useConnection, useLaptopContext, useMedia } from '../../store/remote.ts'
import { useUi, type PlayerMode } from '../../store/ui.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { Card, EmptyState, SegmentedControl, Skeleton } from '../../ui/primitives.tsx'
import { Slider } from '../../ui/Slider.tsx'
import { PresentationView } from './PresentationView.tsx'
import { QuickLaunch, TimerPill } from './extras.tsx'
import { Artwork, AppBadge } from './parts.tsx'
import { Scrubber } from './Scrubber.tsx'

const MODES: readonly { value: Mode; label: string }[] = [
  { value: 'music', label: 'Player' },
  { value: 'movie', label: 'Movie' },
  { value: 'presentation', label: 'Slides' },
]

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => {
      setNow(Date.now())
    }, 250)
    return () => {
      clearInterval(timer)
    }
  }, [active])
  return now
}

function effectiveMode(mode: PlayerMode): Mode {
  return mode === 'auto' ? 'music' : mode
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
            {s.status === 'playing' && <span className="sr-only"> (playing)</span>}
          </button>
        )
      })}
    </div>
  )
}

function Transport({ session, big = false }: { session: MediaSession; big?: boolean }) {
  const target = { sessionId: session.id }
  const playing = session.status === 'playing'
  return (
    <div className="flex items-center justify-between">
      <IconButton label="Previous" size="lg" variant="plain" disabled={!session.canPrev} onClick={() => { client.send('media.prev', target) }}>
        <SkipBack className="h-7 w-7" fill="currentColor" />
      </IconButton>
      <IconButton label="Back 10 seconds" size="lg" variant="plain" onClick={() => { client.send('media.seek', { ...target, by: -10 }) }}>
        <RotateCcw className="h-7 w-7" />
      </IconButton>
      <IconButton
        label={playing ? 'Pause' : 'Play'}
        size="xl"
        variant="solid"
        className={big ? 'h-28 w-28' : ''}
        onClick={() => { client.send('media.toggle', target) }}
      >
        {playing ? <Pause className="h-9 w-9" fill="currentColor" /> : <Play className="ml-1 h-9 w-9" fill="currentColor" />}
      </IconButton>
      <IconButton label="Forward 10 seconds" size="lg" variant="plain" onClick={() => { client.send('media.seek', { ...target, by: 10 }) }}>
        <RotateCw className="h-7 w-7" />
      </IconButton>
      <IconButton label="Next" size="lg" variant="plain" disabled={!session.canNext} onClick={() => { client.send('media.next', target) }}>
        <SkipForward className="h-7 w-7" fill="currentColor" />
      </IconButton>
    </div>
  )
}

function VolumeCard() {
  const { volume } = useMedia()
  if (volume === null) return null
  return (
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
  )
}

function TrackInfo({ session }: { session: MediaSession }) {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <AppBadge session={session} />
      <h1 className="w-full truncate text-2xl font-semibold">{session.title || 'Unknown title'}</h1>
      {session.artist !== '' && <p className="w-full truncate text-base text-[var(--color-text-secondary)]">{session.artist}</p>}
    </div>
  )
}

function MusicView({ session, now }: { session: MediaSession; now: number }) {
  return (
    <>
      <Artwork session={session} image={mediaStore.artwork.get(session.artworkId)} />
      <TrackInfo session={session} />
      <Scrubber
        position={positionAt(session, now)}
        duration={session.duration}
        canSeek={session.canSeek}
        onSeek={(to) => {
          client.send('media.seek', { sessionId: session.id, to })
        }}
      />
      <Transport session={session} />
    </>
  )
}

function KeyAction({ label, keyName, icon }: { label: string; keyName: KeyName; icon: React.ReactNode }) {
  return (
    <Button
      size="lg"
      className="flex-1"
      icon={icon}
      onClick={() => {
        client.send('key.press', { key: keyName, modifiers: [] })
      }}
    >
      {label}
    </Button>
  )
}

function MovieView({ session, now }: { session: MediaSession; now: number }) {
  const context = useLaptopContext((s) => s.context)
  const owner = useConnection((s) => s.session?.role === 'owner')
  const keys = movieKeys(context)
  return (
    <>
      <TrackInfo session={session} />
      <Scrubber
        position={positionAt(session, now)}
        duration={session.duration}
        canSeek={session.canSeek}
        onSeek={(to) => {
          client.send('media.seek', { sessionId: session.id, to })
        }}
      />
      <div className="py-6">
        <Transport session={session} big />
      </div>
      {owner && (
        <div className="flex flex-wrap gap-3">
          <KeyAction label="Fullscreen" keyName={keys.fullscreen} icon={<Expand className="h-5 w-5" aria-hidden="true" />} />
          {keys.subtitles !== null && (
            <KeyAction label="Subtitles" keyName={keys.subtitles} icon={<Captions className="h-5 w-5" aria-hidden="true" />} />
          )}
          {keys.skipIntro !== null && (
            <KeyAction label="Skip intro" keyName={keys.skipIntro} icon={<SkipForward className="h-5 w-5" aria-hidden="true" />} />
          )}
        </div>
      )}
    </>
  )
}

export function NowPlayingTab() {
  const { media } = useMedia()
  const mode = useUi((s) => s.mode)
  const setMode = useUi((s) => s.setMode)
  const session = media === null ? null : currentSession(media)
  const now = useNow(session?.status === 'playing')
  const view = effectiveMode(mode)

  if (media === null) {
    return (
      <div className="flex flex-col gap-4 pt-2">
        <Skeleton label="Loading what's playing" className="aspect-square w-full" />
        <Skeleton label="Loading controls" className="h-24 w-full" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 pt-2">
      <TimerPill />
      <SegmentedControl
        label="Controls"
        options={MODES}
        value={view}
        onChange={(m) => {
          setMode(m)
        }}
      />
      {view === 'presentation' ? (
        <PresentationView />
      ) : (
        <>
          <SessionChips sessions={media.sessions} currentId={session?.id ?? null} />
          {session === null ? (
            <EmptyState
              icon={view === 'movie' ? <Monitor className="h-10 w-10" /> : <Music2 className="h-10 w-10" />}
              title="Nothing playing"
              body="Start something on your laptop, or open one of these."
              action={<QuickLaunch />}
            />
          ) : view === 'movie' ? (
            <MovieView session={session} now={now} />
          ) : (
            <MusicView session={session} now={now} />
          )}
        </>
      )}
      <VolumeCard />
    </div>
  )
}
