/**
 * Glue between DOM pointer events and the pure gesture machine: owns the
 * machine, the sender and the animation-frame loop (timers, inertia, coalescing).
 */
import { InputSender, type SenderOptions } from './sender.ts'
import type { TrackpadSettings } from './settings.ts'
import { TrackpadMachine, type MachineConfig } from './trackpad.ts'

export interface FrameScheduler {
  request(callback: () => void): number
  cancel(handle: number): void
  now(): number
}

const browserScheduler: FrameScheduler = {
  request: (cb) => requestAnimationFrame(cb),
  cancel: (h) => {
    cancelAnimationFrame(h)
  },
  now: () => performance.now(),
}

export interface PointerSample {
  pointerId: number
  x: number
  y: number
  t: number
}

export function machineConfig(settings: TrackpadSettings, width: number, height: number): MachineConfig {
  return {
    width,
    height,
    sensitivity: settings.sensitivity,
    acceleration: settings.acceleration,
    naturalScroll: settings.naturalScroll,
    tapToClick: settings.tapToClick,
    scrollPxPerNotch: settings.scrollPxPerNotch,
  }
}

export class TrackpadController {
  private readonly machine: TrackpadMachine
  private readonly sender: InputSender
  private readonly scheduler: FrameScheduler
  private settings: TrackpadSettings
  private size = { width: 1, height: 1 }
  private handle: number | null = null

  constructor(settings: TrackpadSettings, sender: SenderOptions, scheduler: FrameScheduler = browserScheduler) {
    this.settings = settings
    this.scheduler = scheduler
    this.machine = new TrackpadMachine(machineConfig(settings, 1, 1))
    this.sender = new InputSender(sender)
  }

  configure(settings: TrackpadSettings, sender: SenderOptions): void {
    this.settings = settings
    this.sender.configure(sender)
    this.machine.configure(machineConfig(settings, this.size.width, this.size.height))
  }

  resize(width: number, height: number): void {
    this.size = { width, height }
    this.machine.configure(machineConfig(this.settings, width, height))
  }

  get dragLocked(): boolean {
    return this.machine.isDragLocked
  }

  down(s: PointerSample): void {
    this.sender.push(this.machine.down(s.pointerId, s.x, s.y, s.t))
    this.ensureLoop()
  }

  move(samples: readonly PointerSample[]): void {
    for (const s of samples) this.sender.push(this.machine.move(s.pointerId, s.x, s.y, s.t))
    this.ensureLoop()
  }

  up(s: PointerSample): void {
    this.sender.push(this.machine.up(s.pointerId, s.x, s.y, s.t))
    this.ensureLoop()
  }

  cancel(pointerId: number): void {
    this.sender.push(this.machine.cancel(pointerId, this.scheduler.now()))
    this.ensureLoop()
  }

  /** End every gesture and any drag (view hidden or unmounted). */
  reset(): void {
    if (this.handle !== null) this.scheduler.cancel(this.handle)
    this.handle = null
    this.sender.push(this.machine.reset())
    this.sender.flush()
    this.sender.clear()
  }

  private readonly tick = (): void => {
    this.handle = null
    this.sender.push(this.machine.frame(this.scheduler.now()))
    this.sender.flush()
    if (!this.machine.idle) this.ensureLoop()
  }

  private ensureLoop(): void {
    this.handle ??= this.scheduler.request(this.tick)
  }
}
