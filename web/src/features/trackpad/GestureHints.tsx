const HINTS: [string, string][] = [
  ['Move', 'Slide one finger'],
  ['Click', 'Tap'],
  ['Right click', 'Tap with two fingers'],
  ['Scroll', 'Slide two fingers, or use the right edge'],
  ['Drag', 'Tap then hold and slide, or press and hold'],
  ['Zoom', 'Pinch'],
  ['Switch apps and tabs', 'Swipe with three fingers'],
]

/** A faint list of gestures, shown until the first touch of the session. */
export function GestureHints() {
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm text-zinc-400">
        {HINTS.map(([name, how]) => (
          <div key={name} className="contents">
            <dt className="font-medium text-zinc-300">{name}</dt>
            <dd>{how}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
