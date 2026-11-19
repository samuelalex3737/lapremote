import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { useUi } from '../store/ui.ts'
import { springs } from './motion.ts'

const SHOW_MS = 3500

const TONE = {
  info: 'text-[var(--color-text)]',
  success: 'text-[var(--color-success)]',
  warn: 'text-[var(--color-warn)]',
  error: 'text-[var(--color-danger)]',
} as const

/** One toast at a time, top of the screen, below the status bar. */
export function ToastHost() {
  const toast = useUi((s) => s.toast)
  const dismiss = useUi((s) => s.dismissToast)

  useEffect(() => {
    if (toast === null) return
    const timer = setTimeout(() => {
      dismiss(toast.id)
    }, SHOW_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [toast, dismiss])

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 z-50 flex justify-center px-4"
      style={{ top: 'max(0.75rem, env(safe-area-inset-top))' }}
    >
      <AnimatePresence>
        {toast !== null && (
          <motion.p
            key={toast.id}
            initial={{ opacity: 0, y: -16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -16, scale: 0.96 }}
            transition={springs.snappy}
            className={`glass pointer-events-auto max-w-md rounded-2xl px-4 py-3 text-sm font-medium ${TONE[toast.level]}`}
            onClick={() => {
              dismiss(toast.id)
            }}
          >
            {toast.message}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
