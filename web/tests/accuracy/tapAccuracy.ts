/**
 * Tap-to-click accuracy, end to end on the real screen:
 *
 *   1. A full-screen browser opens the agent's /calibration page (5 pink targets).
 *   2. A headless "phone" page connects to the agent, takes a full-resolution preview
 *      frame and finds the targets in it (pixel colour), as normalised coordinates.
 *   3. It sends input.absclick for each target. The agent moves the real cursor and clicks.
 *   4. The calibration page reports how far (physical px) each click landed from its target.
 *
 *   node tests/accuracy/tapAccuracy.ts <port> <deviceId> <token>
 *
 * The agent must run WITHOUT --input-dry-run. This takes over the mouse for ~10 seconds.
 */
import { chromium } from '@playwright/test'

const [portArg, deviceId, token] = process.argv.slice(2)
if (portArg === undefined || deviceId === undefined || token === undefined) {
  console.error('usage: node tests/accuracy/tapAccuracy.ts <port> <deviceId> <token>')
  process.exit(2)
}
const base = `http://127.0.0.1:${portArg}`
const LIMIT_PX = 10

interface Target {
  x: number
  y: number
  pixels: number
}

// Installed Chrome with a throwaway profile: the bundled Chromium can't start headed here.
const screen = await chromium.launch({ headless: false, channel: 'chrome', args: ['--start-fullscreen'] })
const phoneBrowser = await chromium.launch()
try {
  const calibration = await (await screen.newContext({ viewport: null })).newPage()
  await calibration.goto(`${base}/calibration`)
  await calibration.bringToFront()
  await calibration.waitForTimeout(1500)

  const phone = await phoneBrowser.newPage()
  await phone.goto(`${base}/api/health`)
  const found = await phone.evaluate(
    async ({ deviceId, token }) => {
      const ws = new WebSocket(`ws://${location.host}/ws`)
      ws.binaryType = 'arraybuffer'
      ;(window as unknown as { __ws: WebSocket }).__ws = ws
      const frames: ArrayBuffer[] = []
      let authed: () => void = () => undefined
      const ok = new Promise<void>((resolve) => {
        authed = resolve
      })
      ws.onmessage = (e) => {
        if (typeof e.data === 'string') {
          if ((JSON.parse(e.data) as { type: string }).type === 'auth.ok') authed()
        } else {
          frames.push(e.data as ArrayBuffer)
          const n = new DataView(e.data as ArrayBuffer).getUint32(0)
          ws.send(JSON.stringify({ v: 1, id: `a${String(n)}`, type: 'preview.ack', payload: { frame: n } }))
        }
      }
      await new Promise((resolve) => {
        ws.onopen = resolve
      })
      ws.send(JSON.stringify({ v: 1, id: 'r', type: 'auth.resume', payload: { deviceId, token } }))
      await ok
      ws.send(JSON.stringify({ v: 1, id: 'p', type: 'preview.start', payload: { fps: 2, width: 1920, monitor: 0 } }))
      while (frames.length < 4) await new Promise((r) => setTimeout(r, 100))
      ws.send(JSON.stringify({ v: 1, id: 's', type: 'preview.stop', payload: {} }))
      const last = frames.at(-1)
      if (last === undefined) throw new Error("no frame")
      const bmp = await createImageBitmap(new Blob([new Uint8Array(last, 8)], { type: 'image/jpeg' }))
      const canvas = new OffscreenCanvas(bmp.width, bmp.height)
      const ctx = canvas.getContext('2d')
      if (ctx === null) throw new Error('no 2d context')
      ctx.drawImage(bmp, 0, 0)
      const { data } = ctx.getImageData(0, 0, bmp.width, bmp.height)
      const clusters: { sx: number; sy: number; n: number }[] = []
      for (let y = 0; y < bmp.height; y += 1) {
        for (let x = 0; x < bmp.width; x += 1) {
          const i = (y * bmp.width + x) * 4
          const r = data[i] ?? 0
          const g = data[i + 1] ?? 0
          const b = data[i + 2] ?? 0
          if (r < 170 || b < 170 || g > 110) continue
          const near = clusters.find((c) => Math.hypot(c.sx / c.n - x, c.sy / c.n - y) < 60)
          if (near !== undefined) {
            near.sx += x
            near.sy += y
            near.n += 1
          } else clusters.push({ sx: x, sy: y, n: 1 })
        }
      }
      return {
        width: bmp.width,
        height: bmp.height,
        targets: clusters
          .filter((c) => c.n > 200)
          .map((c) => ({ x: c.sx / c.n / bmp.width, y: c.sy / c.n / bmp.height, pixels: c.n })),
      }
    },
    { deviceId, token },
  )
  console.log(`frame ${String(found.width)}x${String(found.height)}, targets found: ${String(found.targets.length)}`)
  if (found.targets.length !== 5) throw new Error(`expected 5 targets in the frame, found ${String(found.targets.length)}`)

  await calibration.bringToFront()
  const acks = await phone.evaluate(async (targets: Target[]) => {
    const ws = (window as unknown as { __ws: WebSocket }).__ws
    const results: string[] = []
    const pending = new Map<string, (ok: string) => void>()
    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return
      const m = JSON.parse(e.data) as { type: string; payload: { id: string; ok: boolean; error: string | null } }
      if (m.type === 'ack') pending.get(m.payload.id)?.(m.payload.ok ? 'ok' : (m.payload.error ?? 'failed'))
    }
    for (const [n, t] of targets.entries()) {
      const id = `c${String(n)}`
      const done = new Promise<string>((resolve) => pending.set(id, resolve))
      ws.send(JSON.stringify({ v: 1, id, type: 'input.absclick', payload: { x: t.x, y: t.y, monitor: 0, button: 'left' } }))
      results.push(await done)
      await new Promise((r) => setTimeout(r, 400))
    }
    ws.close()
    return results
  }, found.targets)
  console.log(`clicks acked: ${acks.join(', ')}`)

  await calibration.waitForTimeout(500)
  const hits = await calibration.evaluate(
    () => (window as unknown as { __calibration: { target: number; distancePx: number; x: number; y: number }[] }).__calibration,
  )
  for (const [n, h] of hits.entries()) {
    console.log(`tap ${String(n + 1)}: target ${String(h.target + 1)} at (${String(h.x)}, ${String(h.y)}) ${String(h.distancePx)} px off`)
  }
  const distinct = new Set(hits.map((h) => h.target)).size
  const worst = Math.max(...hits.map((h) => h.distancePx))
  console.log(`targets hit: ${String(distinct)}/5, worst error ${String(worst)} px (limit ${String(LIMIT_PX)} px)`)
  if (hits.length !== 5 || distinct !== 5 || worst > LIMIT_PX) process.exitCode = 1
} finally {
  await phoneBrowser.close()
  await screen.close()
}
