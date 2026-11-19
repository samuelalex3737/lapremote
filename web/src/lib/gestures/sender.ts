/**
 * Turns trackpad actions into protocol messages.
 *
 * Moves and scrolls are coalesced to at most one message each per animation
 * frame, with the sub-pixel / sub-step remainder carried to the next frame.
 * Discrete actions (clicks, buttons, zoom, swipes) flush pending motion first so
 * ordering is preserved, then go out immediately.
 */
import type { ClientPayload, ClientType } from '../protocol.ts'
import { comboFor, type HostOs } from './combos.ts'
import type { ThreeFingerAction, SwipeDirection } from './settings.ts'
import type { Action, HapticPattern } from './trackpad.ts'

export type Send = <T extends ClientType>(type: T, payload: ClientPayload<T>) => void

/** Scroll precision on the wire: 1/120 notch matches Windows' wheel resolution. */
export const SCROLL_QUANTUM = 1 / 120

export interface SenderOptions {
  send: Send
  os: HostOs
  canClick: boolean
  threeFinger: Record<SwipeDirection, ThreeFingerAction>
  onHaptic?: (pattern: HapticPattern) => void
}

export class InputSender {
  private opts: SenderOptions
  private moveX = 0
  private moveY = 0
  private scrollX = 0
  private scrollY = 0

  constructor(opts: SenderOptions) {
    this.opts = opts
  }

  configure(opts: SenderOptions): void {
    this.opts = opts
  }

  push(actions: readonly Action[]): void {
    for (const action of actions) this.handle(action)
  }

  private handle(action: Action): void {
    const { send, canClick } = this.opts
    switch (action.kind) {
      case 'move':
        this.moveX += action.dx
        this.moveY += action.dy
        return
      case 'scroll':
        if (!canClick) return
        this.scrollX += action.dx
        this.scrollY += action.dy
        return
      case 'haptic':
        this.opts.onHaptic?.(action.pattern)
        return
      default:
        break
    }
    if (!canClick) return
    this.flush()
    switch (action.kind) {
      case 'click':
        send('input.click', { button: action.button })
        return
      case 'down':
        send('input.down', { button: action.button })
        return
      case 'up':
        send('input.up', { button: action.button })
        return
      case 'zoom':
        send('input.zoom', { dir: action.dir })
        return
      case 'swipe': {
        const combo = comboFor(this.opts.os, this.opts.threeFinger[action.dir])
        if (combo !== null) send('key.press', { key: combo.key, modifiers: combo.modifiers })
        return
      }
    }
  }

  /** Send the accumulated motion. Call once per animation frame. */
  flush(): void {
    const mx = Math.trunc(this.moveX)
    const my = Math.trunc(this.moveY)
    if (mx !== 0 || my !== 0) {
      this.moveX -= mx
      this.moveY -= my
      this.opts.send('input.move', { dx: mx, dy: my })
    }
    const sx = Math.trunc(this.scrollX / SCROLL_QUANTUM) * SCROLL_QUANTUM
    const sy = Math.trunc(this.scrollY / SCROLL_QUANTUM) * SCROLL_QUANTUM
    if (sx !== 0 || sy !== 0) {
      this.scrollX -= sx
      this.scrollY -= sy
      this.opts.send('input.scroll', { dx: round(sx), dy: round(sy) })
    }
  }

  /** Drop any carried remainder (for example after a reconnect). */
  clear(): void {
    this.moveX = 0
    this.moveY = 0
    this.scrollX = 0
    this.scrollY = 0
  }
}

function round(value: number): number {
  return Math.round(value * 1e6) / 1e6
}
