import { AnimatePresence, motion, useDragControls } from 'motion/react'
import { useEffect, useId, type ReactNode } from 'react'
import { springs } from './motion.ts'

interface Props {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

/** Bottom sheet: drag the handle (or swipe down fast) to close, tap the backdrop or press Esc. */
export function Sheet({ open, title, onClose, children }: Props) {
  const controls = useDragControls()
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-40 flex items-end justify-center">
          <motion.button
            type="button"
            aria-label="Close"
            className="absolute inset-0 bg-black/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="glass relative flex max-h-[88dvh] w-full max-w-lg flex-col rounded-t-[28px] pb-safe"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={springs.gentle}
            drag="y"
            dragControls={controls}
            dragListener={false}
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.6 }}
            onDragEnd={(_e, info) => {
              if (info.offset.y > 120 || info.velocity.y > 600) onClose()
            }}
          >
            <div
              className="flex cursor-grab touch-none flex-col items-center gap-3 px-5 pt-3 pb-2"
              onPointerDown={(e) => {
                controls.start(e)
              }}
            >
              <span className="h-1.5 w-10 rounded-full bg-[var(--color-line-strong)]" aria-hidden="true" />
              <h2 id={titleId} className="self-start text-lg font-semibold">
                {title}
              </h2>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
