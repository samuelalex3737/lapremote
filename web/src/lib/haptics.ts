/**
 * Haptic feedback through navigator.vibrate. Android supports it; iOS Safari does
 * not, so every call is a silent no-op there.
 */
export const HAPTIC_PATTERNS = {
  click: 8,
  rightClick: 15,
  dragLock: [10, 40, 10],
  tick: 4,
} as const satisfies Record<string, number | number[]>

export type HapticName = keyof typeof HAPTIC_PATTERNS

type Vibrate = (pattern: number | number[]) => boolean

function browserVibrate(): Vibrate | null {
  const nav = globalThis.navigator as (Navigator & { vibrate?: Vibrate }) | undefined
  if (nav === undefined || typeof nav.vibrate !== 'function') return null
  return nav.vibrate.bind(nav)
}

export function haptic(name: HapticName, vibrate: Vibrate | null = browserVibrate()): boolean {
  if (vibrate === null) return false
  const pattern = HAPTIC_PATTERNS[name]
  try {
    return vibrate(typeof pattern === 'number' ? pattern : [...pattern])
  } catch {
    return false
  }
}
