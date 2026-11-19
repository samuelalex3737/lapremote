import { create } from 'zustand'
import { loadSettings, saveSettings, type TrackpadSettings } from '../../lib/gestures/settings.ts'

interface TrackpadSettingsState {
  settings: TrackpadSettings
  set: (settings: TrackpadSettings) => void
}

/** Trackpad settings shared by the trackpad and the Settings screen, saved on the phone. */
export const useTrackpadSettingsStore = create<TrackpadSettingsState>((set) => ({
  settings: loadSettings(),
  set: (settings) => {
    saveSettings(settings)
    set({ settings })
  },
}))

export function useTrackpadSettings(): [TrackpadSettings, (settings: TrackpadSettings) => void] {
  const settings = useTrackpadSettingsStore((s) => s.settings)
  const set = useTrackpadSettingsStore((s) => s.set)
  return [settings, set]
}
