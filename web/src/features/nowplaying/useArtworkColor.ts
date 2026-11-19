import { FastAverageColor } from 'fast-average-color'
import { useEffect, useState } from 'react'
import type { Rgb } from '../../lib/color.ts'

const fac = new FastAverageColor()
const cache = new Map<string, Rgb>()

/** Average colour of an artwork image (cached by artwork id), or null while unknown. */
export function useArtworkColor(artworkId: string | null, dataUrl: string | null): Rgb | null {
  const cached = artworkId !== null ? (cache.get(artworkId) ?? null) : null
  const [color, setColor] = useState<{ id: string; rgb: Rgb } | null>(null)

  useEffect(() => {
    if (artworkId === null || dataUrl === null || cache.has(artworkId)) return
    let cancelled = false
    fac
      .getColorAsync(dataUrl, { algorithm: 'dominant', ignoredColor: [[0, 0, 0, 255, 20], [255, 255, 255, 255, 20]] })
      .then((result) => {
        const rgb: Rgb = [result.value[0], result.value[1], result.value[2]]
        cache.set(artworkId, rgb)
        if (!cancelled) setColor({ id: artworkId, rgb })
      })
      .catch(() => {
        // Unreadable image: keep the default accent.
      })
    return () => {
      cancelled = true
    }
  }, [artworkId, dataUrl])

  if (cached !== null) return cached
  return color !== null && color.id === artworkId ? color.rgb : null
}
