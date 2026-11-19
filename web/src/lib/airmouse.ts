/**
 * Air mouse: turns the phone's rotation rate into cursor moves.
 *
 * Hold the phone like a TV remote, screen up and the top pointing at the laptop.
 * Turning left or right is rotation about the screen's normal (rotationRate.alpha);
 * tilting the top up or down is rotation about the phone's left-right axis
 * (rotationRate.beta). Both are degrees per second.
 */

export interface RotationRate {
  alpha: number | null
  beta: number | null
  gamma: number | null
}

export interface AirSettings {
  /** Cursor pixels per degree of rotation. */
  pxPerDegree: number
  /** Rotation slower than this (deg/s) is treated as hand tremor and ignored. */
  deadZone: number
  /** Exponential smoothing factor in (0, 1]. 1 means no smoothing. */
  smoothing: number
}

export const DEFAULT_AIR: AirSettings = { pxPerDegree: 14, deadZone: 3, smoothing: 0.35 }

export interface AirState {
  x: number
  y: number
}

export const AIR_REST: AirState = { x: 0, y: 0 }

/** Largest step between two motion events that is still trusted (ms). */
const MAX_DT_MS = 100

function deadZone(rate: number, zone: number): number {
  if (Math.abs(rate) <= zone) return 0
  // Subtract the zone so motion starts smoothly from zero instead of jumping.
  return rate - Math.sign(rate) * zone
}

/**
 * One motion sample in, one cursor delta out. Pure: the caller keeps `state`.
 * Returns pixels to move for this sample, plus the new smoothing state.
 */
export function airStep(
  rate: RotationRate,
  dtMs: number,
  state: AirState,
  settings: AirSettings = DEFAULT_AIR,
): { dx: number; dy: number; state: AirState } {
  const yaw = deadZone(rate.alpha ?? 0, settings.deadZone)
  const pitch = deadZone(rate.beta ?? 0, settings.deadZone)
  const a = Math.min(1, Math.max(0.01, settings.smoothing))
  const next = { x: state.x + a * (-yaw - state.x), y: state.y + a * (-pitch - state.y) }
  const dt = Math.min(Math.max(dtMs, 0), MAX_DT_MS) / 1000
  return { dx: next.x * dt * settings.pxPerDegree, dy: next.y * dt * settings.pxPerDegree, state: next }
}

type PermissionFn = () => Promise<'granted' | 'denied' | 'default'>

/** iOS asks for motion access from a tap. Everywhere else it is already allowed. */
export async function requestMotionPermission(): Promise<boolean> {
  const ctor = (globalThis as { DeviceMotionEvent?: { requestPermission?: PermissionFn } }).DeviceMotionEvent
  if (ctor === undefined) return false
  if (typeof ctor.requestPermission !== 'function') return true
  try {
    return (await ctor.requestPermission()) === 'granted'
  } catch {
    return false
  }
}
