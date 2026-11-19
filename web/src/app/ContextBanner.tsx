import { X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { suggestMode } from '../lib/adaptive.ts'
import { useLaptopContext } from '../store/remote.ts'
import { useUi } from '../store/ui.ts'
import { IconButton } from '../ui/Button.tsx'

/**
 * Slides in when what is in focus on the laptop suggests a better control surface
 * ("Netflix in focus - movie controls"), with a one-tap switch. With auto-switch on,
 * the switch happens by itself (never away from the trackpad mid-use).
 */
export function ContextBanner() {
  const context = useLaptopContext((s) => s.context)
  const { tab, mode, dismissedBanner, autoSwitch, setMode, setTab, dismissBanner } = useUi()
  const suggestion = suggestMode(context)
  const effective = mode === 'auto' ? 'music' : mode
  const alreadyThere = suggestion !== null && suggestion.mode === effective && tab === 'now'

  useEffect(() => {
    if (!autoSwitch || suggestion === null) return
    setMode(suggestion.mode)
    if (tab !== 'trackpad') setTab('now')
    // Only react to the context changing, not to tab changes the person makes afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSwitch, suggestion?.key])

  const show = suggestion !== null && !alreadyThere && dismissedBanner !== suggestion.key && !autoSwitch

  return (
    <AnimatePresence mode="wait">
      {show && (
        <motion.div
          key={suggestion.key}
          initial={{ opacity: 0, y: -12, height: 0 }}
          animate={{ opacity: 1, y: 0, height: 'auto' }}
          exit={{ opacity: 0, y: -12, height: 0 }}
          // Quick on purpose: a focus change must show the new banner within a second.
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="overflow-hidden px-4"
        >
          <div className="glass mb-2 flex items-center gap-2 rounded-2xl py-1.5 pr-1.5 pl-4">
            <p className="min-w-0 flex-1 truncate text-sm font-medium">{suggestion.text}</p>
            <button
              type="button"
              className="min-h-11 shrink-0 rounded-full bg-[var(--color-accent)] px-4 text-sm font-semibold text-[var(--color-accent-contrast)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-text)]"
              onClick={() => {
                setMode(suggestion.mode)
                setTab('now')
              }}
            >
              Switch
            </button>
            <IconButton
              label="Dismiss"
              variant="plain"
              onClick={() => {
                dismissBanner(suggestion.key)
              }}
            >
              <X className="h-5 w-5" />
            </IconButton>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
