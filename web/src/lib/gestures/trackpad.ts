/**
 * Trackpad gesture state machine. Pure: it takes pointer events with explicit
 * timestamps and returns the actions to perform. Timers (long press, inertia)
 * advance through `frame(t)`, called once per animation frame.
 */
import { accelerate } from './acceleration.ts'
import type { SwipeDirection } from './settings.ts'

export type MouseButton = 'left' | 'right' | 'middle'
export type HapticPattern = 'click' | 'rightClick' | 'dragLock'

export type Action =
  | { kind: 'move'; dx: number; dy: number }
  | { kind: 'click'; button: MouseButton }
  | { kind: 'down'; button: MouseButton }
  | { kind: 'up'; button: MouseButton }
  /** Wheel notches. dy > 0 moves the view down the page. */
  | { kind: 'scroll'; dx: number; dy: number }
  | { kind: 'zoom'; dir: 'in' | 'out' }
  | { kind: 'swipe'; dir: SwipeDirection }
  | { kind: 'haptic'; pattern: HapticPattern }

export interface MachineConfig {
  width: number
  height: number
  sensitivity: number
  acceleration: number
  naturalScroll: boolean
  tapToClick: boolean
  scrollPxPerNotch: number
}

export const TIMING = {
  tapMaxMs: 180,
  tapMaxMovePx: 6,
  tapDragWindowMs: 250,
  longPressMs: 450,
  twoTapMaxMs: 200,
  twoTapMaxMovePx: 8,
  /** Zoom step size once a pinch has started. */
  pinchRatio: 0.08,
  pinchDebounceMs: 120,
  /** A pinch starts only when the gap between the fingers changed by this many px... */
  pinchStartPx: 24,
  /** ...and by this fraction of the starting gap. */
  pinchStartRatio: 0.15,
  twoFingerScrollStartPx: 10,
  /** Scroll wins when the fingers moved together this many times more than their gap changed. */
  scrollDominance: 1.5,
  swipeMinPx: 40,
  edgeStripFraction: 0.12,
  inertiaDecay: 0.95,
  inertiaStopPx: 0.5,
  frameMs: 1000 / 60,
} as const

interface Pointer {
  startX: number
  startY: number
  x: number
  y: number
  t: number
  maxMove: number
}

type Mode =
  | 'pending' // one finger, not decided yet (could be a tap)
  | 'move' // cursor movement (button held when drag-locked)
  | 'tapDrag' // tap then hold-drag: button is down
  | 'locking' // long press fired the drag lock; finger still down
  | 'edgeScroll' // right-edge scroll bar
  | 'multiPending' // two fingers, not decided yet
  | 'scroll'
  | 'pinch'
  | 'swipe' // three fingers, not fired yet
  | 'done' // gesture consumed (swipe fired, or fingers lifting after a multi-finger gesture)

interface Gesture {
  mode: Mode
  startT: number
  maxFingers: number
  edge: boolean
  tapDragCandidate: boolean
  multiStartT: number
  baseDistance: number
  baseCentroid: { x: number; y: number }
  lastCentroid: { x: number; y: number }
  lastCentroidT: number
  lastZoomT: number
  velocity: { x: number; y: number }
}

function centroid(points: Pointer[]): { x: number; y: number } {
  const n = points.length
  return {
    x: points.reduce((s, p) => s + p.x, 0) / n,
    y: points.reduce((s, p) => s + p.y, 0) / n,
  }
}

function distance(points: Pointer[]): number {
  const [a, b] = points
  if (a === undefined || b === undefined) return 0
  return Math.hypot(a.x - b.x, a.y - b.y)
}

export class TrackpadMachine {
  private config: MachineConfig
  private readonly pointers = new Map<number, Pointer>()
  private gesture: Gesture | null = null
  private lastTapUpT: number | null = null
  private dragLocked = false
  private inertia: { x: number; y: number } | null = null
  /** Set when the first of two fingers lifts quickly and still: the second lift decides. */
  private twoTapEligible = false

  constructor(config: MachineConfig) {
    this.config = config
  }

  configure(config: MachineConfig): void {
    this.config = config
  }

  get isDragLocked(): boolean {
    return this.dragLocked
  }

  /** True when nothing needs frame() calls: no fingers down and no inertia running. */
  get idle(): boolean {
    return this.pointers.size === 0 && this.inertia === null
  }

  // ------------------------------------------------------------------ helpers

  private toNotches(fingerDx: number, fingerDy: number, natural: boolean): { dx: number; dy: number } {
    // Natural: content follows the fingers, so fingers moving up show content further down.
    const sign = natural ? -1 : 1
    return {
      dx: (sign * fingerDx) / this.config.scrollPxPerNotch,
      dy: (sign * fingerDy) / this.config.scrollPxPerNotch,
    }
  }

  private accel(dx: number, dy: number, dt: number): Action {
    const out = accelerate(dx, dy, dt, {
      base: this.config.sensitivity,
      k: this.config.acceleration,
    })
    return { kind: 'move', dx: out.dx, dy: out.dy }
  }

  private active(): Pointer[] {
    return [...this.pointers.values()]
  }

  // ------------------------------------------------------------------ events

  down(id: number, x: number, y: number, t: number): Action[] {
    const actions: Action[] = []
    this.inertia = null
    this.pointers.set(id, { startX: x, startY: y, x, y, t, maxMove: 0 })
    const count = this.pointers.size

    if (this.gesture === null || count === 1) {
      const tapDragCandidate =
        !this.dragLocked &&
        this.config.tapToClick &&
        this.lastTapUpT !== null &&
        t - this.lastTapUpT <= TIMING.tapDragWindowMs
      this.gesture = {
        mode: 'pending',
        startT: t,
        maxFingers: 1,
        edge: x >= this.config.width * (1 - TIMING.edgeStripFraction),
        tapDragCandidate,
        multiStartT: t,
        baseDistance: 0,
        baseCentroid: { x, y },
        lastCentroid: { x, y },
        lastCentroidT: t,
        lastZoomT: -Infinity,
        velocity: { x: 0, y: 0 },
      }
      return actions
    }

    const g = this.gesture
    g.maxFingers = Math.max(g.maxFingers, count)
    if (g.mode === 'tapDrag' || g.mode === 'locking' || (g.mode === 'move' && this.dragLocked)) {
      // Extra fingers during a drag are ignored so the drag can't be broken by accident.
      return actions
    }
    const points = this.active()
    g.multiStartT = t
    g.baseCentroid = centroid(points)
    g.lastCentroid = g.baseCentroid
    g.lastCentroidT = t
    g.baseDistance = distance(points)
    g.velocity = { x: 0, y: 0 }
    if (count === 2) g.mode = g.mode === 'pending' || g.mode === 'move' ? 'multiPending' : 'done'
    else if (count === 3) g.mode = 'swipe'
    else g.mode = 'done'
    return actions
  }

  move(id: number, x: number, y: number, t: number): Action[] {
    const p = this.pointers.get(id)
    const g = this.gesture
    if (p === undefined || g === null) return []
    const dx = x - p.x
    const dy = y - p.y
    const dt = t - p.t
    p.x = x
    p.y = y
    p.t = t
    p.maxMove = Math.max(p.maxMove, Math.hypot(x - p.startX, y - p.startY))
    if (dx === 0 && dy === 0) return []
    const count = this.pointers.size

    if (count === 1) return this.moveOne(p, dx, dy, dt, t)
    if (count === 2) return this.moveTwo(t)
    if (count === 3) return this.moveThree()
    return []
  }

  private moveOne(p: Pointer, dx: number, dy: number, dt: number, t: number): Action[] {
    const g = this.gesture
    if (g === null) return []
    switch (g.mode) {
      case 'pending': {
        if (p.maxMove < TIMING.tapMaxMovePx) {
          // Below the tap threshold: move the cursor (it's still a tap if released now),
          // except in the edge strip, which waits to see if this is a scroll.
          return g.edge ? [] : [this.accel(dx, dy, dt)]
        }
        const totalDx = p.x - p.startX
        const totalDy = p.y - p.startY
        if (g.edge && Math.abs(totalDy) > Math.abs(totalDx)) {
          g.mode = 'edgeScroll'
          // Scroll-bar semantics: finger down moves the view down.
          return [{ kind: 'scroll', dx: 0, dy: totalDy / this.config.scrollPxPerNotch }]
        }
        if (g.tapDragCandidate) {
          g.mode = 'tapDrag'
          return [{ kind: 'down', button: 'left' }, this.accel(dx, dy, dt)]
        }
        g.mode = 'move'
        if (g.edge) return [this.accel(totalDx, totalDy, Math.max(t - g.startT, 1))]
        return [this.accel(dx, dy, dt)]
      }
      case 'move':
      case 'tapDrag':
      case 'locking':
        return [this.accel(dx, dy, dt)]
      case 'edgeScroll':
        return [{ kind: 'scroll', dx: 0, dy: dy / this.config.scrollPxPerNotch }]
      case 'multiPending':
      case 'scroll':
      case 'pinch':
      case 'swipe':
      case 'done':
        // One finger left over from a multi-finger gesture: ignore until it lifts.
        return []
    }
  }

  private moveTwo(t: number): Action[] {
    const g = this.gesture
    if (g === null) return []
    const points = this.active()
    const c = centroid(points)
    const dist = distance(points)
    const actions: Action[] = []

    if (g.mode === 'multiPending') {
      // Decide by comparing, in pixels, how far the fingers travelled together with how much
      // the gap between them changed. A ratio alone misfires when the fingers start close
      // together: a 4px drift on a 40px gap is already 10%.
      const travel = Math.hypot(c.x - g.baseCentroid.x, c.y - g.baseCentroid.y)
      const spreadChange = Math.abs(dist - g.baseDistance)
      const isScroll =
        travel > TIMING.twoFingerScrollStartPx && travel >= spreadChange * TIMING.scrollDominance
      const isPinch =
        !isScroll &&
        spreadChange >= TIMING.pinchStartPx &&
        spreadChange >= g.baseDistance * TIMING.pinchStartRatio &&
        spreadChange > travel
      if (isPinch) {
        g.mode = 'pinch'
        actions.push({ kind: 'zoom', dir: dist > g.baseDistance ? 'in' : 'out' })
        g.baseDistance = dist
        g.lastZoomT = t
      } else if (isScroll) {
        g.mode = 'scroll'
        actions.push({
          kind: 'scroll',
          ...this.toNotches(c.x - g.baseCentroid.x, c.y - g.baseCentroid.y, this.config.naturalScroll),
        })
      }
    } else if (g.mode === 'scroll') {
      const ddx = c.x - g.lastCentroid.x
      const ddy = c.y - g.lastCentroid.y
      const dt = Math.max(t - g.lastCentroidT, 1)
      // Smoothed finger velocity in px per frame, used for inertia after lift.
      const vx = (ddx / dt) * TIMING.frameMs
      const vy = (ddy / dt) * TIMING.frameMs
      g.velocity = { x: g.velocity.x * 0.5 + vx * 0.5, y: g.velocity.y * 0.5 + vy * 0.5 }
      if (ddx !== 0 || ddy !== 0) {
        actions.push({ kind: 'scroll', ...this.toNotches(ddx, ddy, this.config.naturalScroll) })
      }
    } else if (g.mode === 'pinch') {
      const ratio = g.baseDistance > 0 ? dist / g.baseDistance : 1
      if (Math.abs(ratio - 1) > TIMING.pinchRatio && t - g.lastZoomT >= TIMING.pinchDebounceMs) {
        actions.push({ kind: 'zoom', dir: ratio > 1 ? 'in' : 'out' })
        g.baseDistance = dist
        g.lastZoomT = t
      }
    }
    g.lastCentroid = c
    g.lastCentroidT = t
    return actions
  }

  private moveThree(): Action[] {
    const g = this.gesture
    if (g?.mode !== 'swipe') return []
    const c = centroid(this.active())
    const dx = c.x - g.baseCentroid.x
    const dy = c.y - g.baseCentroid.y
    if (Math.max(Math.abs(dx), Math.abs(dy)) <= TIMING.swipeMinPx) return []
    g.mode = 'done'
    const dir: SwipeDirection =
      Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : dy > 0 ? 'down' : 'up'
    return [{ kind: 'swipe', dir }]
  }

  up(id: number, x: number, y: number, t: number): Action[] {
    const actions = this.move(id, x, y, t)
    return [...actions, ...this.release(id, t)]
  }

  cancel(id: number, t: number): Action[] {
    return this.release(id, t, true)
  }

  private release(id: number, t: number, cancelled = false): Action[] {
    const p = this.pointers.get(id)
    const g = this.gesture
    if (p === undefined || g === null) return []
    this.pointers.delete(id)
    if (this.pointers.size > 0) {
      if (g.mode === 'multiPending' || g.mode === 'scroll' || g.mode === 'pinch' || g.mode === 'swipe') {
        // Keep the multi-finger gesture until every finger is up.
        if (g.mode === 'multiPending') this.finishTwoFingerTap(g, p, t)
      }
      return []
    }
    const actions = cancelled ? this.finishCancelled(g) : this.finish(g, p, t)
    this.gesture = null
    return actions
  }

  private finishTwoFingerTap(g: Gesture, p: Pointer, t: number): void {
    // Called when the first of two fingers lifts in multiPending mode.
    const others = this.active()
    this.twoTapEligible =
      g.maxFingers === 2 &&
      t - g.multiStartT <= TIMING.twoTapMaxMs &&
      p.maxMove < TIMING.twoTapMaxMovePx &&
      others.every((o) => o.maxMove < TIMING.twoTapMaxMovePx)
    g.mode = this.twoTapEligible ? 'multiPending' : 'done'
  }

  private finish(g: Gesture, p: Pointer, t: number): Action[] {
    if (g.maxFingers === 1) return this.finishOne(g, p, t)
    if (g.maxFingers === 2) {
      if (g.mode === 'scroll') {
        const v = g.velocity
        if (Math.hypot(v.x, v.y) >= TIMING.inertiaStopPx) this.inertia = { ...v }
        return []
      }
      if (
        g.mode === 'multiPending' &&
        this.twoTapEligible &&
        t - g.multiStartT <= TIMING.twoTapMaxMs &&
        p.maxMove < TIMING.twoTapMaxMovePx
      ) {
        this.twoTapEligible = false
        if (!this.config.tapToClick) return []
        return [
          { kind: 'click', button: 'right' },
          { kind: 'haptic', pattern: 'rightClick' },
        ]
      }
    }
    this.twoTapEligible = false
    return []
  }

  private finishOne(g: Gesture, p: Pointer, t: number): Action[] {
    const isTap = t - g.startT < TIMING.tapMaxMs && p.maxMove < TIMING.tapMaxMovePx
    switch (g.mode) {
      case 'tapDrag':
        this.lastTapUpT = null
        return [{ kind: 'up', button: 'left' }]
      case 'locking':
        // The long-press finger lifted: stay locked until the next tap.
        return []
      case 'move':
      case 'edgeScroll':
        return []
      case 'pending':
        if (!isTap) return []
        if (this.dragLocked) {
          this.dragLocked = false
          this.lastTapUpT = null
          return [
            { kind: 'up', button: 'left' },
            { kind: 'haptic', pattern: 'click' },
          ]
        }
        if (!this.config.tapToClick) return []
        // A second tap right after a tap is not a drag start, so it can't chain a third.
        this.lastTapUpT = g.tapDragCandidate ? null : t
        return [
          { kind: 'click', button: 'left' },
          { kind: 'haptic', pattern: 'click' },
        ]
      case 'multiPending':
      case 'scroll':
      case 'pinch':
      case 'swipe':
      case 'done':
        return []
    }
  }

  private finishCancelled(g: Gesture): Action[] {
    this.twoTapEligible = false
    if (g.mode === 'tapDrag') return [{ kind: 'up', button: 'left' }]
    return []
  }

  /** Advance timers: long-press drag lock and scroll inertia. */
  frame(t: number): Action[] {
    const actions: Action[] = []
    const g = this.gesture
    if (
      g !== null &&
      g.mode === 'pending' &&
      g.maxFingers === 1 &&
      !this.dragLocked &&
      !g.tapDragCandidate &&
      t - g.startT >= TIMING.longPressMs
    ) {
      const p = this.active()[0]
      if (p !== undefined && p.maxMove < TIMING.tapMaxMovePx) {
        g.mode = 'locking'
        this.dragLocked = true
        this.lastTapUpT = null
        actions.push({ kind: 'haptic', pattern: 'dragLock' }, { kind: 'down', button: 'left' })
      }
    }
    if (this.inertia !== null) {
      const v = this.inertia
      actions.push({ kind: 'scroll', ...this.toNotches(v.x, v.y, this.config.naturalScroll) })
      const next = { x: v.x * TIMING.inertiaDecay, y: v.y * TIMING.inertiaDecay }
      this.inertia = Math.hypot(next.x, next.y) < TIMING.inertiaStopPx ? null : next
    }
    return actions
  }

  /** Stop inertia (for example when the view unmounts) and end any drag. */
  reset(): Action[] {
    const actions: Action[] = []
    const g = this.gesture
    if ((g !== null && g.mode === 'tapDrag') || this.dragLocked) {
      actions.push({ kind: 'up', button: 'left' })
    }
    this.pointers.clear()
    this.gesture = null
    this.inertia = null
    this.dragLocked = false
    this.lastTapUpT = null
    this.twoTapEligible = false
    return actions
  }
}
