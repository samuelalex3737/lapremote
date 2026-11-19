import { THREE_FINGER_LABELS } from '../../lib/gestures/combos.ts'
import {
  DEFAULT_SETTINGS,
  THREE_FINGER_ACTIONS,
  type SwipeDirection,
  type ThreeFingerAction,
  type TrackpadSettings,
} from '../../lib/gestures/settings.ts'

interface Props {
  settings: TrackpadSettings
  onChange: (settings: TrackpadSettings) => void
  onClose: () => void
}

const DIRECTIONS: [SwipeDirection, string][] = [
  ['up', 'Swipe up'],
  ['down', 'Swipe down'],
  ['left', 'Swipe left'],
  ['right', 'Swipe right'],
]

function Range(props: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
  format: (value: number) => string
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="flex justify-between text-sm">
        <span className="font-medium">{props.label}</span>
        <span className="tabular-nums text-zinc-400">{props.format(props.value)}</span>
      </span>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => {
          props.onChange(Number(e.target.value))
        }}
        className="h-11 w-full accent-white"
      />
    </label>
  )
}

function Toggle(props: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex min-h-11 items-center justify-between gap-4">
      <span className="text-sm font-medium">{props.label}</span>
      <input
        type="checkbox"
        role="switch"
        checked={props.checked}
        onChange={(e) => {
          props.onChange(e.target.checked)
        }}
        className="h-6 w-6 accent-white"
      />
    </label>
  )
}

export function TrackpadSettingsPanel({ settings, onChange, onClose }: Props) {
  const set = (patch: Partial<TrackpadSettings>) => {
    onChange({ ...settings, ...patch })
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="trackpad-settings-title"
      className="fixed inset-0 z-20 flex flex-col bg-[#0b0b10]/95 px-4 backdrop-blur"
      style={{
        paddingTop: 'max(1rem, env(safe-area-inset-top))',
        paddingBottom: 'max(1rem, env(safe-area-inset-bottom))',
      }}
    >
      <div className="mx-auto flex w-full max-w-md items-center justify-between py-2">
        <h2 id="trackpad-settings-title" className="text-xl font-semibold">
          Trackpad settings
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="min-h-11 rounded-full bg-zinc-100 px-5 text-sm font-semibold text-zinc-900"
        >
          Done
        </button>
      </div>
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col gap-5 overflow-y-auto py-4">
        <Range
          label="Pointer speed"
          value={settings.sensitivity}
          min={0.5}
          max={4}
          step={0.1}
          format={(v) => `${v.toFixed(1)}x`}
          onChange={(sensitivity) => {
            set({ sensitivity })
          }}
        />
        <Range
          label="Acceleration"
          value={settings.acceleration}
          min={0}
          max={2}
          step={0.1}
          format={(v) => (v === 0 ? 'Off' : v.toFixed(1))}
          onChange={(acceleration) => {
            set({ acceleration })
          }}
        />
        <Range
          label="Scroll speed"
          value={86 - settings.scrollPxPerNotch}
          min={6}
          max={80}
          step={2}
          format={(v) => `${String(Math.round(((v - 6) / 74) * 100))}%`}
          onChange={(v) => {
            set({ scrollPxPerNotch: 86 - v })
          }}
        />
        <Toggle
          label="Natural scrolling"
          checked={settings.naturalScroll}
          onChange={(naturalScroll) => {
            set({ naturalScroll })
          }}
        />
        <Toggle
          label="Tap to click"
          checked={settings.tapToClick}
          onChange={(tapToClick) => {
            set({ tapToClick })
          }}
        />
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-sm font-medium">Three-finger swipes</legend>
          {DIRECTIONS.map(([dir, label]) => (
            <label key={dir} className="flex min-h-11 items-center justify-between gap-4 text-sm">
              <span>{label}</span>
              <select
                value={settings.threeFinger[dir]}
                onChange={(e) => {
                  set({
                    threeFinger: {
                      ...settings.threeFinger,
                      [dir]: e.target.value as ThreeFingerAction,
                    },
                  })
                }}
                className="min-h-11 rounded-xl border border-white/15 bg-zinc-900 px-3"
              >
                {THREE_FINGER_ACTIONS.map((action) => (
                  <option key={action} value={action}>
                    {THREE_FINGER_LABELS[action]}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>
        <button
          type="button"
          onClick={() => {
            onChange(DEFAULT_SETTINGS)
          }}
          className="min-h-11 self-start text-sm text-zinc-400 underline underline-offset-4"
        >
          Reset to defaults
        </button>
      </div>
    </div>
  )
}
