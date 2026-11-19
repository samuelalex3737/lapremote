/** Sleep-timer display helpers. */
import { positionAt } from './media.ts'
import type { MediaSession } from './protocol.ts'

export const TIMER_PRESETS = [15, 30, 45, 60, 90] as const

export function remainingSeconds(endsAt: number | null, nowMs: number): number {
  return endsAt === null ? 0 : Math.max(0, Math.round((endsAt - nowMs) / 1000))
}

/** "End of this episode" is only possible when the player reports a duration. */
export function endOfMediaSeconds(session: MediaSession | null, nowMs: number): number | null {
  if (session?.duration == null) return null
  const position = positionAt(session, nowMs)
  if (position === null) return null
  return Math.max(0, (session.duration - position) / Math.max(session.rate, 0.01))
}

export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = String(m).padStart(h > 0 ? 2 : 1, '0')
  return `${h > 0 ? `${String(h)}:` : ''}${mm}:${String(sec).padStart(2, '0')}`
}
