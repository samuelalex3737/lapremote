/**
 * Screen preview helpers: frame header parsing and mapping a tap on the (zoomed,
 * letterboxed) preview back to normalised 0..1 coordinates on the laptop monitor.
 */
import { PREVIEW_HEADER_BYTES } from './protocol.ts'

export interface PreviewFrame {
  frame: number
  monitor: number
  jpeg: Uint8Array
}

/** 8-byte big-endian header (uint32 frame, uint32 monitor) followed by the JPEG bytes. */
export function parseFrame(data: ArrayBuffer): PreviewFrame | null {
  if (data.byteLength <= PREVIEW_HEADER_BYTES) return null
  const view = new DataView(data)
  return {
    frame: view.getUint32(0, false),
    monitor: view.getUint32(4, false),
    jpeg: new Uint8Array(data, PREVIEW_HEADER_BYTES),
  }
}

export interface Size {
  width: number
  height: number
}

export interface View {
  scale: number
  tx: number
  ty: number
}

export const IDENTITY: View = { scale: 1, tx: 0, ty: 0 }
export const MAX_ZOOM = 5

/** Where an image of `image` size sits inside `box` with object-fit: contain. */
export function containRect(box: Size, image: Size): { left: number; top: number; width: number; height: number } {
  if (image.width <= 0 || image.height <= 0 || box.width <= 0 || box.height <= 0) {
    return { left: 0, top: 0, width: 0, height: 0 }
  }
  const scale = Math.min(box.width / image.width, box.height / image.height)
  const width = image.width * scale
  const height = image.height * scale
  return { left: (box.width - width) / 2, top: (box.height - height) / 2, width, height }
}

/**
 * A tap at (px, py) in container coordinates -> normalised image coordinates, undoing
 * the zoom transform (scale about the top-left, then translate). Null outside the image.
 */
export function tapToNormalised(px: number, py: number, box: Size, image: Size, view: View): { x: number; y: number } | null {
  const rect = containRect(box, image)
  if (rect.width === 0) return null
  const ux = (px - view.tx) / view.scale
  const uy = (py - view.ty) / view.scale
  const x = (ux - rect.left) / rect.width
  const y = (uy - rect.top) / rect.height
  if (x < 0 || x > 1 || y < 0 || y > 1) return null
  return { x, y }
}

/** Keep the zoomed content covering the container: no panning past the edges. */
export function clampView(view: View, box: Size): View {
  const scale = Math.min(MAX_ZOOM, Math.max(1, view.scale))
  const minTx = box.width - box.width * scale
  const minTy = box.height - box.height * scale
  return {
    scale,
    tx: Math.min(0, Math.max(minTx, view.tx)),
    ty: Math.min(0, Math.max(minTy, view.ty)),
  }
}

/** Zoom by `factor` keeping the container point (cx, cy) fixed under the fingers. */
export function zoomAt(view: View, factor: number, cx: number, cy: number, box: Size): View {
  const scale = Math.min(MAX_ZOOM, Math.max(1, view.scale * factor))
  const k = scale / view.scale
  return clampView({ scale, tx: cx - (cx - view.tx) * k, ty: cy - (cy - view.ty) * k }, box)
}
