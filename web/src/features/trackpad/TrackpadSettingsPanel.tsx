import { THREE_FINGER_LABELS } from '../../lib/gestures/combos.ts'
import {
  DEFAULT_SETTINGS,
  THREE_FINGER_ACTIONS,
  type SwipeDirection,
  type ThreeFingerAction,
  type TrackpadSettings,
} from '../../lib/gestures/settings.ts'
import { Button } from '../../ui/Button.tsx'
import { Switch } from '../../ui/primitives.tsx'
import { Sheet } from '../../ui/Sheet.tsx'
import { Slider } from '../../ui/Slider.tsx'

const DIRECTIONS: [SwipeDirection, string][] = [
  ['up', 'Swipe up'],
  ['down', 'Swipe down'],
  ['left', 'Swipe left'],
  ['right', 'Swipe right'],
]

interface FormProps {
  settings: TrackpadSettings
  onChange: (settings: TrackpadSettings) => void
}

export function TrackpadSettingsForm({ settings, onChange }: FormProps) {
  const set = (patch: Partial<TrackpadSettings>) => {
    onChange({ ...settings, ...patch })
  }
  return (
    <div className="flex flex-col gap-4">
      <Slider
        label="Pointer speed"
        value={settings.sensitivity}
        min={0.5}
        max={4}
        step={0.1}
        valueText={`${settings.sensitivity.toFixed(1)}x`}
        onChange={(sensitivity) => {
          set({ sensitivity })
        }}
      />
      <Slider
        label="Acceleration"
        value={settings.acceleration}
        min={0}
        max={2}
        step={0.1}
        valueText={settings.acceleration === 0 ? 'Off' : settings.acceleration.toFixed(1)}
        onChange={(acceleration) => {
          set({ acceleration })
        }}
      />
      <Slider
        label="Scroll speed"
        value={86 - settings.scrollPxPerNotch}
        min={6}
        max={80}
        step={2}
        valueText={`${String(Math.round(((80 - settings.scrollPxPerNotch) / 74) * 100))}%`}
        onChange={(v) => {
          set({ scrollPxPerNotch: 86 - v })
        }}
      />
      <Switch
        label="Natural scrolling"
        description="Content follows your fingers"
        checked={settings.naturalScroll}
        onChange={(naturalScroll) => {
          set({ naturalScroll })
        }}
      />
      <Switch
        label="Tap to click"
        checked={settings.tapToClick}
        onChange={(tapToClick) => {
          set({ tapToClick })
        }}
      />
      <fieldset className="flex flex-col gap-1">
        <legend className="pb-2 text-sm font-medium">Three-finger swipes</legend>
        {DIRECTIONS.map(([dir, label]) => (
          <label key={dir} className="flex min-h-12 items-center justify-between gap-4 text-sm">
            <span>{label}</span>
            <select
              value={settings.threeFinger[dir]}
              onChange={(e) => {
                set({ threeFinger: { ...settings.threeFinger, [dir]: e.target.value as ThreeFingerAction } })
              }}
              className="min-h-11 rounded-xl bg-[var(--color-bg-raised)] px-3 ring-1 ring-inset ring-[var(--color-line-strong)]"
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
      <Button
        variant="ghost"
        className="self-start underline underline-offset-4"
        onClick={() => {
          onChange(DEFAULT_SETTINGS)
        }}
      >
        Reset to defaults
      </Button>
    </div>
  )
}

export function TrackpadSettingsPanel(props: FormProps & { open: boolean; onClose: () => void }) {
  return (
    <Sheet open={props.open} title="Trackpad settings" onClose={props.onClose}>
      <TrackpadSettingsForm settings={props.settings} onChange={props.onChange} />
    </Sheet>
  )
}
