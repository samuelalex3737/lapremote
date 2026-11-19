/** Pointer acceleration: gain = base * (1 + k * min(speed, cap)), speed in px/ms. */
export const SPEED_CAP_PX_PER_MS = 2.5

export interface AccelerationOptions {
  base: number
  k: number
  cap?: number
}

export function gainFor(speed: number, { base, k, cap = SPEED_CAP_PX_PER_MS }: AccelerationOptions): number {
  return base * (1 + k * Math.min(Math.max(speed, 0), cap))
}

export function accelerate(
  dx: number,
  dy: number,
  dtMs: number,
  options: AccelerationOptions,
): { dx: number; dy: number } {
  const speed = Math.hypot(dx, dy) / Math.max(dtMs, 1)
  const gain = gainFor(speed, options)
  return { dx: dx * gain, dy: dy * gain }
}
