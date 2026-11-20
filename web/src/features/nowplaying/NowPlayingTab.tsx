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
    <div
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 land:mx-0 land:min-w-0 land:px-0 land:pb-0"
      data-no-swipe
      role="tablist"
      aria-label="Players"
    >
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
        className={big ? 'h-24 w-24 short:h-20 short:w-20 land:h-20 land:w-20' : ''}
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
    <Card className="flex items-center gap-3 py-1.5">
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
    <div className="flex flex-col items-start gap-1">
      <AppBadge session={session} />
      <h1 className="w-full truncate text-xl font-semibold">{session.title || 'Unknown title'}</h1>
      {session.artist !== '' && <p className="w-full truncate text-base text-[var(--color-text-secondary)]">{session.artist}</p>}
    </div>
  )
}

/**
 * Stacked in portrait. Side by side when the phone is held sideways, so the controls never
 * fall below the fold. `grow` marks the side that takes the spare height in portrait.
 */
function Split({ left, right, grow }: { left: React.ReactNode; right: React.ReactNode; grow: 'left' | 'right' }) {
  const side = 'flex min-h-0 flex-col gap-3 short:gap-2 land:flex-1 land:justify-center'
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 short:gap-2 land:flex-row land:gap-5">
      <div className={`${side} ${grow === 'left' ? 'flex-1' : ''}`}>{left}</div>
      <div className={`${side} ${grow === 'right' ? 'flex-1' : ''}`}>{right}</div>
    </div>
  )
}

function MusicView({ session, now }: { session: MediaSession; now: number }) {
  return (
    <Split
      grow="left"
      left={
        <>
          {/* The artwork takes whatever height is left, so the controls always fit on screen. */}
          <div className="flex min-h-[72px] flex-1 items-center justify-center">
            <Artwork session={session} image={mediaStore.artwork.get(session.artworkId)} />
          </div>
          <TrackInfo session={session} />
        </>
      }
      right={
        <>
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
      }
    />
  )
}

function KeyAction({ label, keyName, icon }: { label: string; keyName: KeyName; icon: React.ReactNode }) {
  return (
    <Button
      size="lg"
      className="flex-1 short:min-h-11 land:min-h-11"
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
    <Split
      grow="right"
      left={
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
        </>
      }
      right={
        <>
          <div className="flex flex-1 flex-col justify-center py-2 short:py-0 land:flex-none land:py-0">
            <Transport session={session} big />
          </div>
          {owner && (
            <div className="flex flex-wrap gap-3 short:gap-2">
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
      }
    />
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
    <div className="flex min-h-0 flex-1 flex-col gap-3 pt-1 short:gap-2 land:gap-2">
      <TimerPill />
      <div className="flex flex-col gap-3 short:gap-2 land:flex-row land:items-center land:gap-3">
        <div className="land:w-1/2 land:shrink-0">
          <SegmentedControl
            label="Controls"
            options={MODES}
            value={view}
            onChange={(m) => {
              setMode(m)
            }}
          />
        </div>
        {view !== 'presentation' && <SessionChips sessions={media.sessions} currentId={session?.id ?? null} />}
      </div>
      {view === 'presentation' ? (
        <PresentationView />
      ) : (
        <>
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
