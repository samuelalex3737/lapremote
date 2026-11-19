/** Scrubber maths: pointer position to time, kept pure for testing. */

export function fractionAt(clientX: number, left: number, width: number): number {
  if (width <= 0) return 0
  return Math.min(1, Math.max(0, (clientX - left) / width))
}

export function timeAt(fraction: number, duration: number): number {
  return Math.round(Math.min(1, Math.max(0, fraction)) * duration * 10) / 10
}

/** Seconds per arrow-key step on the scrubber: 5s, or 1% of long media. */
export function keyboardStep(duration: number): number {
  return Math.max(5, Math.round(duration / 100))
}
