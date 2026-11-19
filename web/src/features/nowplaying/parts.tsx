import { AudioLines, Film, Globe, Music2 } from 'lucide-react'
import { motion } from 'motion/react'
import { haptic } from '../../lib/haptics.ts'
import type { MediaSession } from '../../lib/protocol.ts'
import { client } from '../../store/remote.ts'

const BROWSERS = /brave|chrome|edge|firefox|safari|opera|vivaldi|arc|chromium/i
const VIDEO = /vlc|movies|tv|netflix|prime|iina|mpv|quicktime/i
const MUSIC = /spotify|music|itunes|deezer|tidal|foobar|musicbee|rhythmbox/i

function AppIcon({ session }: { session: MediaSession }) {
  const name = `${session.appName} ${session.appId}`
  const props = { className: 'h-3.5 w-3.5', 'aria-hidden': true } as const
  if (BROWSERS.test(name)) return <Globe {...props} />
  if (VIDEO.test(name)) return <Film {...props} />
  if (MUSIC.test(name)) return <Music2 {...props} />
  return <AudioLines {...props} />
}

export function AppBadge({ session }: { session: MediaSession }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-surface-strong)] px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)] ring-1 ring-inset ring-[var(--color-line)]">
      <AppIcon session={session} />
      {session.appName}
    </span>
  )
}

const SWIPE_PX = 80

/** Large artwork with a soft glow; swipe it left for next and right for previous. */
export function Artwork({ session, image }: { session: MediaSession; image: string | null }) {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[340px]" data-no-swipe>
      {image !== null && (
        <img
          src={image}
          alt=""
          aria-hidden="true"
          className="absolute inset-4 h-[calc(100%-2rem)] w-[calc(100%-2rem)] scale-110 rounded-[28px] object-cover opacity-60 blur-2xl"
        />
      )}
      <motion.div
        className="relative h-full w-full cursor-grab overflow-hidden rounded-[28px] bg-[var(--color-surface-strong)] shadow-[var(--shadow-soft)] active:cursor-grabbing"
        drag="x"
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={0.35}
        onDragEnd={(_e, info) => {
          if (info.offset.x <= -SWIPE_PX && session.canNext) {
            haptic('click')
            client.send('media.next', { sessionId: session.id })
          } else if (info.offset.x >= SWIPE_PX && session.canPrev) {
            haptic('click')
            client.send('media.prev', { sessionId: session.id })
          }
        }}
      >
        {image !== null ? (
          <img
            src={image}
            alt={`Artwork for ${session.title || session.appName}`}
            draggable={false}
            className="h-full w-full select-none object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[var(--color-text-tertiary)]">
            <Music2 className="h-16 w-16" aria-hidden="true" />
          </div>
        )}
      </motion.div>
    </div>
  )
}
