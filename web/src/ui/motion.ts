import type { Transition } from 'motion/react'

/** Spring presets shared by every animated component. */
export const springs = {
  snappy: { type: 'spring', stiffness: 520, damping: 38, mass: 0.8 },
  gentle: { type: 'spring', stiffness: 220, damping: 28 },
} as const satisfies Record<string, Transition>
