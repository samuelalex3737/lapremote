import { X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { IconButton } from '../ui/Button.tsx'
import type { ContextSuggestion } from './useContextSuggestion.ts'

/** The suggestion as one compact row that shares the header with the connection status. */
export function ContextBanner({ suggestion }: { suggestion: ContextSuggestion }) {
  const current = suggestion.suggestion
  return (
    <AnimatePresence mode="wait" initial={false}>
      {current !== null && (
        <motion.div
          key={current.key}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          // Quick on purpose: a focus change must show the new suggestion within a second.
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="glass flex min-w-0 flex-1 items-center gap-1 rounded-full py-0.5 pr-0.5 pl-3"
        >
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{current.text}</p>
          <button
            type="button"
            className="min-h-11 shrink-0 rounded-full bg-[var(--color-accent)] px-4 text-sm font-semibold text-[var(--color-accent-contrast)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-text)]"
            onClick={suggestion.accept}
          >
            Switch
          </button>
          <IconButton label="Dismiss" variant="plain" onClick={suggestion.dismiss}>
            <X className="h-5 w-5" />
          </IconButton>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
