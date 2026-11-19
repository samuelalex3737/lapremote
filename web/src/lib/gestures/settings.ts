import { z } from 'zod'

export const THREE_FINGER_ACTIONS = ['task_view', 'show_desktop', 'prev_tab', 'next_tab', 'none'] as const
export type ThreeFingerAction = (typeof THREE_FINGER_ACTIONS)[number]
export type SwipeDirection = 'up' | 'down' | 'left' | 'right'

export const trackpadSettingsSchema = z.object({
  /** Base pointer gain (cursor px per finger px at slow speed). */
  sensitivity: z.number().min(0.5).max(4),
  /** Acceleration factor k in gain = base * (1 + k * min(speed, cap)). */
  acceleration: z.number().min(0).max(2),
  naturalScroll: z.boolean(),
  tapToClick: z.boolean(),
  /** Finger pixels per wheel notch. Lower is faster. */
  scrollPxPerNotch: z.number().min(6).max(80),
  /** Air mouse: point the phone to move the cursor (secure pages only). */
  airMouse: z.boolean(),
  /** Air mouse cursor pixels per degree of rotation. */
  airSpeed: z.number().min(4).max(40),
  threeFinger: z.object({
    up: z.enum(THREE_FINGER_ACTIONS),
    down: z.enum(THREE_FINGER_ACTIONS),
    left: z.enum(THREE_FINGER_ACTIONS),
    right: z.enum(THREE_FINGER_ACTIONS),
  }),
})
export type TrackpadSettings = z.infer<typeof trackpadSettingsSchema>

export const DEFAULT_SETTINGS: TrackpadSettings = {
  sensitivity: 1.6,
  acceleration: 0.6,
  naturalScroll: true,
  tapToClick: true,
  scrollPxPerNotch: 24,
  airMouse: false,
  airSpeed: 14,
  // Same defaults as gestures.threeFinger in ~/.lapremote/config.json.
  threeFinger: { up: 'task_view', down: 'show_desktop', left: 'prev_tab', right: 'next_tab' },
}

export const SETTINGS_KEY = 'lapremote.trackpad.v1'

function storage(): Storage | null {
  try {
    return globalThis.localStorage
  } catch {
    return null
  }
}

export function loadSettings(store: Storage | null = storage()): TrackpadSettings {
  try {
    const raw = store?.getItem(SETTINGS_KEY)
    if (raw == null) return DEFAULT_SETTINGS
    const merged: unknown = { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as object) }
    const parsed = trackpadSettingsSchema.safeParse(merged)
    return parsed.success ? parsed.data : DEFAULT_SETTINGS
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function saveSettings(settings: TrackpadSettings, store: Storage | null = storage()): void {
  try {
    store?.setItem(SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    // Blocked storage: settings last for this visit only.
  }
}
