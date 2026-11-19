import { useRef, type ReactNode } from 'react'
import { haptic } from '../lib/haptics.ts'

interface Props {
  label: string
  value: number
  min?: number
  max?: number
  step?: number
  onChange: (value: number) => void
  onCommit?: (value: number) => void
  /** Text shown for screen readers and next to the label. */
  valueText?: string
  icon?: ReactNode
  hideLabel?: boolean
}

/**
 * Big-touch slider on top of a native range input (keyboard and screen readers
 * work), with a haptic tick every 10% of the range.
 */
export function Slider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
  onCommit,
  valueText,
  icon,
  hideLabel = false,
}: Props) {
  const lastDecile = useRef(Math.floor(((value - min) / (max - min)) * 10))
  const pct = ((value - min) / (max - min)) * 100

  return (
    <label className="flex w-full flex-col gap-2" data-no-swipe>
      {!hideLabel && (
        <span className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2 font-medium">
            {icon}
            {label}
          </span>
          {valueText !== undefined && (
            <span className="tabular-nums text-[var(--color-text-secondary)]">{valueText}</span>
          )}
        </span>
      )}
      <span className="relative flex h-11 items-center">
        <span className="absolute inset-x-0 h-2.5 overflow-hidden rounded-full bg-[var(--color-surface-strong)]">
          <span className="block h-full rounded-full bg-[var(--color-text)]" style={{ width: `${String(pct)}%` }} />
        </span>
        <input
          type="range"
          aria-label={hideLabel ? label : undefined}
          aria-valuetext={valueText}
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => {
            const next = Number(e.target.value)
            const decile = Math.floor(((next - min) / (max - min)) * 10)
            if (decile !== lastDecile.current) {
              lastDecile.current = decile
              haptic('tick')
            }
            onChange(next)
          }}
          onPointerUp={(e) => onCommit?.(Number(e.currentTarget.value))}
          onKeyUp={(e) => onCommit?.(Number(e.currentTarget.value))}
          className="lr-range relative h-11 w-full cursor-pointer appearance-none bg-transparent"
        />
      </span>
    </label>
  )
}
