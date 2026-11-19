import { describe, expect, it } from 'vitest'
import {
  clampView,
  containRect,
  IDENTITY,
  parseFrame,
  tapToNormalised,
  zoomAt,
} from '../../src/lib/preview.ts'

describe('parseFrame', () => {
  it('reads the big-endian header and the JPEG body', () => {
    const buf = new Uint8Array([0, 0, 1, 2, 0, 0, 0, 1, 0xff, 0xd8, 0xff])
    const frame = parseFrame(buf.buffer)
    expect(frame?.frame).toBe(258)
    expect(frame?.monitor).toBe(1)
    expect(Array.from(frame?.jpeg ?? [])).toEqual([0xff, 0xd8, 0xff])
  })

  it('rejects frames without a body', () => {
    expect(parseFrame(new Uint8Array(8).buffer)).toBeNull()
  })
})

describe('containRect', () => {
  it('letterboxes a 16:9 image in a tall box', () => {
    expect(containRect({ width: 390, height: 600 }, { width: 480, height: 270 })).toEqual({
      left: 0,
      top: (600 - 219.375) / 2,
      width: 390,
      height: 219.375,
    })
  })
})

describe('tapToNormalised', () => {
  const box = { width: 400, height: 300 }
  const image = { width: 480, height: 270 } // fills width: 400x225 at top 37.5

  it('maps the centre and corners', () => {
    expect(tapToNormalised(200, 150, box, image, IDENTITY)).toEqual({ x: 0.5, y: 0.5 })
    expect(tapToNormalised(0, 37.5, box, image, IDENTITY)).toEqual({ x: 0, y: 0 })
    expect(tapToNormalised(400, 262.5, box, image, IDENTITY)).toEqual({ x: 1, y: 1 })
  })

  it('ignores taps on the letterbox bars', () => {
    expect(tapToNormalised(200, 10, box, image, IDENTITY)).toBeNull()
  })

  it('undoes zoom and pan', () => {
    const view = { scale: 2, tx: -200, ty: -150 } // zoomed 2x on the centre
    expect(tapToNormalised(200, 150, box, image, view)).toEqual({ x: 0.5, y: 0.5 })
    const left = tapToNormalised(0, 150, box, image, view)
    expect(left?.x).toBeCloseTo(0.25)
  })
})

describe('zoom', () => {
  const box = { width: 400, height: 300 }

  it('keeps the pinch centre fixed and clamps to 1..5x', () => {
    const z = zoomAt(IDENTITY, 2, 200, 150, box)
    expect(z).toEqual({ scale: 2, tx: -200, ty: -150 })
    expect(zoomAt(z, 10, 200, 150, box).scale).toBe(5)
    expect(zoomAt(z, 0.1, 200, 150, box)).toEqual(IDENTITY)
  })

  it('never pans past the edges', () => {
    expect(clampView({ scale: 2, tx: 50, ty: -1000 }, box)).toEqual({ scale: 2, tx: 0, ty: -300 })
  })
})
