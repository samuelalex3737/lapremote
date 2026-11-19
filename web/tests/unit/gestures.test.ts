import { describe, expect, it } from 'vitest'
import { accelerate, gainFor, SPEED_CAP_PX_PER_MS } from '../../src/lib/gestures/acceleration.ts'
import { comboFor, THREE_FINGER_COMBOS } from '../../src/lib/gestures/combos.ts'
import { InputSender } from '../../src/lib/gestures/sender.ts'
import {
  DEFAULT_SETTINGS,
  loadSettings,
  saveSettings,
  SETTINGS_KEY,
} from '../../src/lib/gestures/settings.ts'
import {
  type Action,
  type MachineConfig,
  TIMING,
  TrackpadMachine,
} from '../../src/lib/gestures/trackpad.ts'
import { haptic } from '../../src/lib/haptics.ts'

const CONFIG: MachineConfig = {
  width: 400,
  height: 600,
  sensitivity: 1,
  acceleration: 0,
  naturalScroll: false,
  tapToClick: true,
  scrollPxPerNotch: 10,
}

/** Small driver for writing gesture sequences with explicit times. */
class Driver {
  readonly m: TrackpadMachine
  readonly out: Action[] = []
  t = 1000

  constructor(config: Partial<MachineConfig> = {}) {
    this.m = new TrackpadMachine({ ...CONFIG, ...config })
  }

  at(t: number): this {
    this.t = t
    return this
  }

  wait(ms: number): this {
    // Advance in frame steps so timers fire like they would on screen.
    const end = this.t + ms
    while (this.t < end) {
      this.t = Math.min(this.t + TIMING.frameMs, end)
      this.out.push(...this.m.frame(this.t))
    }
    return this
  }

  down(id: number, x: number, y: number): this {
    this.out.push(...this.m.down(id, x, y, this.t))
    return this
  }

  move(id: number, x: number, y: number, after = 16): this {
    this.t += after
    this.out.push(...this.m.move(id, x, y, this.t))
    return this
  }

  up(id: number, x: number, y: number, after = 0): this {
    this.t += after
    this.out.push(...this.m.up(id, x, y, this.t))
    return this
  }

  kinds(): string[] {
    return this.out.filter((a) => a.kind !== 'haptic').map((a) => a.kind)
  }

  of<K extends Action['kind']>(kind: K): Extract<Action, { kind: K }>[] {
    return this.out.filter((a): a is Extract<Action, { kind: K }> => a.kind === kind)
  }

  clear(): this {
    this.out.length = 0
    return this
  }
}

function sum(actions: { dx: number; dy: number }[]) {
  return actions.reduce((s, a) => ({ dx: s.dx + a.dx, dy: s.dy + a.dy }), { dx: 0, dy: 0 })
}

// ------------------------------------------------------------------ acceleration

describe('acceleration', () => {
  it('follows gain = base * (1 + k * min(speed, cap))', () => {
    expect(gainFor(0, { base: 2, k: 0.5 })).toBe(2)
    expect(gainFor(1, { base: 2, k: 0.5 })).toBe(3)
    expect(gainFor(100, { base: 2, k: 0.5 })).toBe(2 * (1 + 0.5 * SPEED_CAP_PX_PER_MS))
  })

  it('scales deltas by the gain for the speed', () => {
    // 20px in 10ms = 2px/ms
    expect(accelerate(12, 16, 10, { base: 1, k: 1 })).toEqual({ dx: 36, dy: 48 })
    expect(accelerate(3, 4, 0, { base: 1, k: 0 })).toEqual({ dx: 3, dy: 4 })
  })
})

// ------------------------------------------------------------------ one finger

describe('1-finger drag', () => {
  it('moves the cursor', () => {
    const d = new Driver().down(1, 100, 100).move(1, 110, 100).move(1, 130, 105).up(1, 130, 105)
    const moves = d.of('move')
    expect(sum(moves)).toEqual({ dx: 30, dy: 5 })
    expect(d.kinds()).not.toContain('click')
  })

  it('applies acceleration for fast movement', () => {
    const slow = new Driver({ acceleration: 1 }).down(1, 0, 0).move(1, 10, 0, 100)
    const fast = new Driver({ acceleration: 1 }).down(1, 0, 0).move(1, 10, 0, 2)
    expect(sum(fast.of('move')).dx).toBeGreaterThan(sum(slow.of('move')).dx)
  })
})

describe('tap', () => {
  it('is a left click when short and still', () => {
    const d = new Driver().down(1, 100, 100).up(1, 101, 101, 100)
    expect(d.of('click')).toEqual([{ kind: 'click', button: 'left' }])
    expect(d.of('haptic')).toEqual([{ kind: 'haptic', pattern: 'click' }])
  })

  it('is not a tap when it moved 7px', () => {
    const d = new Driver().down(1, 100, 100).move(1, 107, 100).up(1, 107, 100)
    expect(d.of('click')).toEqual([])
  })

  it('is not a tap when held 180ms or more', () => {
    const d = new Driver().down(1, 100, 100).wait(180).up(1, 100, 100)
    expect(d.of('click')).toEqual([])
  })

  it('two quick taps are two clicks (the OS makes the double-click)', () => {
    const d = new Driver()
      .down(1, 100, 100)
      .up(1, 100, 100, 60)
      .wait(80)
      .down(2, 101, 100)
      .up(2, 101, 100, 60)
    expect(d.of('click')).toHaveLength(2)
    expect(d.kinds()).not.toContain('down')
  })

  it('does nothing with tap-to-click off', () => {
    const d = new Driver({ tapToClick: false }).down(1, 100, 100).up(1, 100, 100, 50)
    expect(d.kinds()).toEqual([])
  })
})

describe('tap then hold-drag', () => {
  it('presses, drags and releases', () => {
    const d = new Driver()
      .down(1, 100, 100)
      .up(1, 100, 100, 50)
      .wait(100)
      .down(2, 100, 100)
      .move(2, 110, 100)
      .move(2, 140, 120)
      .up(2, 140, 120)
    expect(d.kinds()).toEqual(['click', 'down', 'move', 'move', 'up'])
    expect(d.of('down')[0]).toEqual({ kind: 'down', button: 'left' })
  })

  it('needs the second press within 250ms of the tap', () => {
    const d = new Driver()
      .down(1, 100, 100)
      .up(1, 100, 100, 50)
      .wait(260)
      .down(2, 100, 100)
      .move(2, 120, 100)
      .up(2, 120, 100)
    expect(d.kinds()).not.toContain('down')
  })
})

describe('long-press drag lock', () => {
  it('locks after 450ms still, drags across lifts, and the next tap releases', () => {
    const d = new Driver().down(1, 100, 100).wait(449)
    expect(d.kinds()).toEqual([])
    d.wait(2)
    expect(d.kinds()).toEqual(['down'])
    expect(d.of('haptic')).toEqual([{ kind: 'haptic', pattern: 'dragLock' }])
    expect(d.m.isDragLocked).toBe(true)

    d.move(1, 140, 100).up(1, 140, 100)
    expect(d.kinds()).toEqual(['down', 'move'])
    expect(d.m.isDragLocked).toBe(true)

    // A new finger keeps dragging.
    d.wait(100).down(2, 200, 200).move(2, 260, 200).up(2, 260, 200)
    expect(d.kinds()).toEqual(['down', 'move', 'move'])

    // The next tap releases instead of clicking.
    d.wait(100).down(3, 200, 200).up(3, 200, 200, 50)
    expect(d.kinds()).toEqual(['down', 'move', 'move', 'up'])
    expect(d.of('click')).toEqual([])
    expect(d.m.isDragLocked).toBe(false)
  })

  it('does not lock if the finger moved first', () => {
    const d = new Driver().down(1, 100, 100).move(1, 120, 100).wait(600)
    expect(d.kinds()).not.toContain('down')
  })
})

describe('right-edge scroll strip', () => {
  it('scrolls vertically without moving the cursor', () => {
    const d = new Driver().down(1, 390, 100).move(1, 390, 104).move(1, 390, 120).move(1, 390, 150)
    expect(d.of('move')).toEqual([])
    expect(sum(d.of('scroll')).dy).toBeCloseTo(5) // 50px / 10px per notch, finger down = view down
  })

  it('becomes a normal move when the motion is horizontal', () => {
    const d = new Driver().down(1, 390, 100).move(1, 370, 101)
    expect(d.of('scroll')).toEqual([])
    expect(sum(d.of('move')).dx).toBe(-20)
  })

  it('a tap in the strip still clicks', () => {
    const d = new Driver().down(1, 395, 100).up(1, 395, 100, 40)
    expect(d.of('click')).toHaveLength(1)
  })
})

// ------------------------------------------------------------------ two fingers

describe('2-finger tap', () => {
  it('is a right click', () => {
    const d = new Driver()
      .down(1, 100, 100)
      .at(1010)
      .down(2, 160, 100)
      .up(1, 101, 100, 80)
      .up(2, 160, 101, 20)
    expect(d.kinds()).toEqual(['click'])
    expect(d.of('click')[0]).toEqual({ kind: 'click', button: 'right' })
    expect(d.of('haptic')).toEqual([{ kind: 'haptic', pattern: 'rightClick' }])
  })

  it('is not a right click when held 200ms or more', () => {
    const d = new Driver().down(1, 100, 100).down(2, 160, 100).wait(210).up(1, 100, 100).up(2, 160, 100)
    expect(d.of('click')).toEqual([])
  })

  it('is not a right click when a finger moved 8px', () => {
    const d = new Driver()
      .down(1, 100, 100)
      .down(2, 160, 100)
      .move(2, 168, 100, 10)
      .up(1, 100, 100, 10)
      .up(2, 168, 100, 10)
    expect(d.of('click')).toEqual([])
  })
})

describe('2-finger scroll', () => {
  it('scrolls with parallel movement', () => {
    const d = new Driver()
      .down(1, 100, 300)
      .down(2, 160, 300)
      .move(1, 100, 280)
      .move(2, 160, 280)
      .move(1, 100, 260)
      .move(2, 160, 260)
    const total = sum(d.of('scroll'))
    expect(total.dy).toBeCloseTo(-4) // fingers up 40px, not natural: view up 4 notches
    expect(d.of('move')).toEqual([])
    expect(d.of('zoom')).toEqual([])
  })

  it('inverts with natural scrolling', () => {
    const d = new Driver({ naturalScroll: true }).down(1, 100, 300).down(2, 160, 300)
    for (let i = 1; i <= 6; i++) d.move(1, 100, 300 - 5 * i).move(2, 160, 300 - 5 * i, 0)
    // Fingers moved up 30px: with natural scrolling the view moves down.
    expect(sum(d.of('scroll')).dy).toBeGreaterThan(0)
    expect(d.of('zoom')).toEqual([])
  })

  it('keeps scrolling with inertia after lift, decaying by 0.95 per frame until < 0.5', () => {
    const d = new Driver().down(1, 100, 300).down(2, 160, 300)
    for (let i = 1; i <= 6; i++) {
      d.move(1, 100, 300 - i * 20)
      d.move(2, 160, 300 - i * 20, 0)
    }
    d.up(1, 100, 180).up(2, 160, 180).clear()
    d.wait(TIMING.frameMs * 3)
    const scrolls = d.of('scroll')
    expect(scrolls.length).toBe(3)
    const [a, b] = scrolls
    expect(Math.abs(b?.dy ?? 0) / Math.abs(a?.dy ?? 1)).toBeCloseTo(0.95)
    d.wait(5000)
    expect(d.m.idle).toBe(true)
    const last = d.of('scroll').at(-1)
    expect(Math.abs((last?.dy ?? 0) * CONFIG.scrollPxPerNotch)).toBeLessThan(0.5 / 0.95 + 1e-9)
  })

  it('a new touch stops inertia', () => {
    const d = new Driver().down(1, 100, 300).down(2, 160, 300)
    for (let i = 1; i <= 4; i++) {
      d.move(1, 100, 300 - i * 20)
      d.move(2, 160, 300 - i * 20, 0)
    }
    d.up(1, 100, 220).up(2, 160, 220).wait(50).down(3, 200, 200).clear()
    d.wait(100)
    expect(d.of('scroll')).toEqual([])
  })
})

describe('pinch', () => {
  it('zooms in and out when the distance changes more than 8%', () => {
    const d = new Driver().down(1, 100, 300).down(2, 200, 300)
    d.move(1, 95, 300).move(2, 205, 300, 0) // 110/100 = +10%
    expect(d.of('zoom')).toEqual([{ kind: 'zoom', dir: 'in' }])
    d.clear()
    d.move(1, 105, 300, 130).move(2, 195, 300, 0) // 90/110 = -18%
    expect(d.of('zoom')).toEqual([{ kind: 'zoom', dir: 'out' }])
  })

  it('debounces steps by 120ms and re-baselines after each step', () => {
    const d = new Driver().down(1, 100, 300).down(2, 200, 300)
    d.move(1, 95, 300).move(2, 205, 300, 0) // step 1 (110)
    d.move(1, 90, 300, 50).move(2, 210, 300, 0) // 120: +9% but only 50ms later
    expect(d.of('zoom')).toHaveLength(1)
    d.move(1, 89, 300, 80) // 130ms after step 1: 121/110 = +10%
    expect(d.of('zoom')).toHaveLength(2)
    d.move(1, 88, 300, 130) // 122/121: under 8% from the new baseline
    expect(d.of('zoom')).toHaveLength(2)
  })

  it('pinch plus drift does not scroll', () => {
    const d = new Driver().down(1, 100, 300).down(2, 200, 300)
    d.move(1, 94, 296).move(2, 206, 296, 0) // spread 12% and drift up 4px
    d.move(1, 94, 270, 16).move(2, 206, 270, 0) // keep drifting up 26px
    expect(d.of('zoom')).toHaveLength(1)
    expect(d.of('scroll')).toEqual([])
  })

  it('does not zoom below the 8% threshold', () => {
    const d = new Driver().down(1, 100, 300).down(2, 200, 300)
    d.move(1, 97, 300).move(2, 203, 300, 0) // 6%
    expect(d.of('zoom')).toEqual([])
  })
})

// ------------------------------------------------------------------ three fingers

describe('3-finger swipe', () => {
  function swipe(dx: number, dy: number) {
    const d = new Driver().down(1, 100, 300).down(2, 150, 300).down(3, 200, 300)
    d.move(1, 100 + dx, 300 + dy).move(2, 150 + dx, 300 + dy, 0).move(3, 200 + dx, 300 + dy, 0)
    return d
  }

  it.each([
    [0, -60, 'up'],
    [0, 60, 'down'],
    [-60, 0, 'left'],
    [60, 0, 'right'],
  ] as const)('swipe (%i, %i) is %s', (dx, dy, dir) => {
    expect(swipe(dx, dy).of('swipe')).toEqual([{ kind: 'swipe', dir }])
  })

  it('needs more than 40px', () => {
    expect(swipe(0, -40).of('swipe')).toEqual([])
  })

  it('fires once per gesture and never clicks', () => {
    const d = swipe(0, -60)
    d.move(1, 100, 100).move(2, 150, 100, 0).move(3, 200, 100, 0)
    d.up(1, 100, 100).up(2, 150, 100).up(3, 200, 100)
    expect(d.of('swipe')).toHaveLength(1)
    expect(d.of('click')).toEqual([])
    expect(d.of('move')).toEqual([])
  })
})

describe('edge cases', () => {
  it('a leftover finger after a 2-finger scroll does not move the cursor', () => {
    const d = new Driver().down(1, 100, 300).down(2, 160, 300)
    d.move(1, 100, 270).move(2, 160, 270, 0).up(2, 160, 270).move(1, 150, 220)
    expect(d.of('move')).toEqual([])
  })

  it('cancel during tap-drag releases the button', () => {
    const d = new Driver().down(1, 100, 100).up(1, 100, 100, 40).wait(50).down(2, 100, 100).move(2, 120, 100)
    d.out.push(...d.m.cancel(2, d.t))
    expect(d.kinds().at(-1)).toBe('up')
  })

  it('reset ends a drag lock', () => {
    const d = new Driver().down(1, 100, 100).wait(500)
    expect(d.m.reset()).toEqual([{ kind: 'up', button: 'left' }])
    expect(d.m.isDragLocked).toBe(false)
  })
})

// ------------------------------------------------------------------ sender

describe('InputSender', () => {
  function make(canClick = true) {
    const sent: { type: string; payload: unknown }[] = []
    const haptics: string[] = []
    const sender = new InputSender({
      send: (type, payload) => sent.push({ type, payload }),
      os: 'windows',
      canClick,
      threeFinger: DEFAULT_SETTINGS.threeFinger,
      onHaptic: (p) => haptics.push(p),
    })
    return { sender, sent, haptics }
  }

  it('coalesces moves to one message per frame and carries the remainder', () => {
    const { sender, sent } = make()
    sender.push([
      { kind: 'move', dx: 1.4, dy: 0.3 },
      { kind: 'move', dx: 1.4, dy: 0.3 },
    ])
    sender.flush()
    expect(sent).toEqual([{ type: 'input.move', payload: { dx: 2, dy: 0 } }])
    sender.push([{ kind: 'move', dx: 0.3, dy: 0.5 }])
    sender.flush()
    expect(sent.at(-1)).toEqual({ type: 'input.move', payload: { dx: 1, dy: 1 } })
  })

  it('flushes motion before a click so order is kept', () => {
    const { sender, sent } = make()
    sender.push([
      { kind: 'move', dx: 5, dy: 0 },
      { kind: 'click', button: 'left' },
    ])
    expect(sent.map((s) => s.type)).toEqual(['input.move', 'input.click'])
  })

  it('maps swipes to key combos for the laptop OS', () => {
    const { sender, sent } = make()
    sender.push([{ kind: 'swipe', dir: 'up' }])
    expect(sent).toEqual([{ type: 'key.press', payload: { key: 'tab', modifiers: ['meta'] } }])
  })

  it('quantises scroll to 1/120 notch and keeps the rest', () => {
    const { sender, sent } = make()
    sender.push([{ kind: 'scroll', dx: 0, dy: 0.5 + 0.001 }])
    sender.flush()
    expect(sent).toEqual([{ type: 'input.scroll', payload: { dx: 0, dy: 0.5 } }])
  })

  it('guests only send moves', () => {
    const { sender, sent, haptics } = make(false)
    sender.push([
      { kind: 'move', dx: 3, dy: 0 },
      { kind: 'click', button: 'left' },
      { kind: 'scroll', dx: 0, dy: 1 },
      { kind: 'haptic', pattern: 'click' },
    ])
    sender.flush()
    expect(sent.map((s) => s.type)).toEqual(['input.move'])
    expect(haptics).toEqual(['click'])
  })
})

describe('combos', () => {
  it('has a combo for every action on every OS', () => {
    for (const os of ['windows', 'macos', 'linux'] as const) {
      for (const action of ['task_view', 'show_desktop', 'prev_tab', 'next_tab'] as const) {
        expect(THREE_FINGER_COMBOS[os][action].key).toBeTruthy()
      }
    }
    expect(comboFor('macos', 'none')).toBeNull()
  })
})

describe('settings', () => {
  class Mem implements Storage {
    map = new Map<string, string>()
    get length() {
      return this.map.size
    }
    clear() {
      this.map.clear()
    }
    getItem(k: string) {
      return this.map.get(k) ?? null
    }
    key(i: number) {
      return [...this.map.keys()][i] ?? null
    }
    removeItem(k: string) {
      this.map.delete(k)
    }
    setItem(k: string, v: string) {
      this.map.set(k, v)
    }
  }

  it('round-trips and falls back to defaults on bad data', () => {
    const mem = new Mem()
    expect(loadSettings(mem)).toEqual(DEFAULT_SETTINGS)
    saveSettings({ ...DEFAULT_SETTINGS, naturalScroll: false }, mem)
    expect(loadSettings(mem).naturalScroll).toBe(false)
    mem.setItem(SETTINGS_KEY, '{"sensitivity": 99}')
    expect(loadSettings(mem)).toEqual(DEFAULT_SETTINGS)
    mem.setItem(SETTINGS_KEY, 'nope')
    expect(loadSettings(mem)).toEqual(DEFAULT_SETTINGS)
  })
})

describe('haptics', () => {
  it('uses the spec patterns and is a no-op without vibrate', () => {
    const calls: unknown[] = []
    const vibrate = (p: number | number[]) => {
      calls.push(p)
      return true
    }
    haptic('click', vibrate)
    haptic('rightClick', vibrate)
    haptic('dragLock', vibrate)
    expect(calls).toEqual([8, 15, [10, 40, 10]])
    expect(haptic('click', null)).toBe(false)
  })
})
