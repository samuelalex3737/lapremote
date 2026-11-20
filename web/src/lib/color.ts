/**
 * Artwork-derived colours: an accent that stays readable on the dark UI and the
 * soft background gradient behind Now Playing.
 */
export type Rgb = readonly [number, number, number]

export function rgbToHsl([r, g, b]: Rgb): [number, number, number] {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h: number
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0)
  else if (max === gn) h = (bn - rn) / d + 2
  else h = (rn - gn) / d + 4
  return [h * 60, s, l]
}

export function hslToRgb([h, s, l]: [number, number, number]): Rgb {
  if (s === 0) {
    const v = Math.round(l * 255)
    return [v, v, v]
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  const hue = (t: number) => {
    let x = t
    if (x < 0) x += 1
    if (x > 1) x -= 1
    if (x < 1 / 6) return p + (q - p) * 6 * x
    if (x < 1 / 2) return q
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6
    return p
  }
  const hn = h / 360
  return [Math.round(hue(hn + 1 / 3) * 255), Math.round(hue(hn) * 255), Math.round(hue(hn - 1 / 3) * 255)]
}

/** Relative luminance (WCAG). */
export function luminance([r, g, b]: Rgb): number {
  const ch = (v: number) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

export function contrast(a: Rgb, b: Rgb): number {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

export const BACKGROUND: Rgb = [7, 7, 11]
/** --color-bg in the light theme. */
export const LIGHT_BACKGROUND: Rgb = [244, 245, 249]

export type Theme = 'dark' | 'light'

/**
 * A vivid accent from the artwork colour that keeps at least 4.5:1 contrast on the
 * app background (lightened until it does). Greys get a gentle default tint.
 */
export function accentFrom(color: Rgb, theme: Theme = 'dark'): Rgb {
  const [h, s, l] = rgbToHsl(color)
  const saturation = s < 0.12 ? 0.35 : Math.min(Math.max(s, 0.45), 0.85)
  const hue = s < 0.12 ? 232 : h
  if (theme === 'light') {
    // On a light page the accent is dark enough for text and carries white labels.
    let light = Math.min(Math.max(l, 0.3), 0.45)
    let rgb = hslToRgb([hue, saturation, light])
    while (contrast(rgb, LIGHT_BACKGROUND) < 4.5 && light > 0.1) {
      light -= 0.03
      rgb = hslToRgb([hue, saturation, light])
    }
    return rgb
  }
  let light = Math.min(Math.max(l, 0.55), 0.82)
  let rgb = hslToRgb([hue, saturation, light])
  while (contrast(rgb, BACKGROUND) < 4.5 && light < 0.95) {
    light += 0.03
    rgb = hslToRgb([hue, saturation, light])
  }
  return rgb
}

export function toCss([r, g, b]: Rgb, alpha = 1): string {
  return alpha === 1 ? `rgb(${String(r)} ${String(g)} ${String(b)})` : `rgb(${String(r)} ${String(g)} ${String(b)} / ${String(alpha)})`
}

/** Background gradient behind Now Playing: the artwork colour fading into the app background. */
export function gradientFrom(color: Rgb, theme: Theme = 'dark'): string {
  const [h, s] = rgbToHsl(color)
  if (theme === 'light') {
    const pale = hslToRgb([h, Math.min(s, 0.55), 0.86])
    return `radial-gradient(120% 70% at 50% 0%, ${toCss(pale, 0.95)} 0%, ${toCss(pale, 0.4)} 45%, ${toCss(LIGHT_BACKGROUND, 0)} 80%)`
  }
  const deep = hslToRgb([h, Math.min(s, 0.6), 0.22])
  return `radial-gradient(120% 70% at 50% 0%, ${toCss(deep, 0.95)} 0%, ${toCss(deep, 0.35)} 45%, ${toCss(BACKGROUND, 0)} 80%)`
}
