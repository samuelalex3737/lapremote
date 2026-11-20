import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { accentFrom, gradientFrom, toCss } from '../../lib/color.ts'
import { currentSession } from '../../lib/media.ts'
import { mediaStore, useMedia } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'
import { useArtworkColor } from './useArtworkColor.ts'

/**
 * The colour wash behind the app while Now Playing is open: derived from the artwork
 * and cross-faded over 600ms between tracks. Also sets the app-wide accent colour.
 */
export function Backdrop({ visible }: { visible: boolean }) {
  const { media } = useMedia()
  const session = media === null ? null : currentSession(media)
  const artworkId = session?.artworkId ?? null
  const color = useArtworkColor(artworkId, mediaStore.artwork.get(artworkId))
  const theme = useUi((s) => s.theme)

  useEffect(() => {
    const root = document.documentElement
    if (color === null) root.style.removeProperty('--accent')
    else root.style.setProperty('--accent', toCss(accentFrom(color, theme)))
  }, [color, theme])

  const key = color === null ? 'none' : `${color.join(',')}-${theme}`
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10">
      <AnimatePresence initial={false}>
        {visible && color !== null && (
          <motion.div
            key={key}
            className="absolute inset-0"
            style={{ background: gradientFrom(color, theme) }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: 'easeInOut' }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
