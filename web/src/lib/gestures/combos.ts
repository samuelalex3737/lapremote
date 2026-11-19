import type { KeyName, Modifier } from '../protocol.ts'
import type { ThreeFingerAction } from './settings.ts'

export type HostOs = 'windows' | 'macos' | 'linux'

export interface KeyCombo {
  key: KeyName
  modifiers: Modifier[]
}

type ComboTable = Record<Exclude<ThreeFingerAction, 'none'>, KeyCombo>

/** Keyboard shortcuts behind each three-finger swipe action, per laptop OS. */
export const THREE_FINGER_COMBOS: Record<HostOs, ComboTable> = {
  windows: {
    task_view: { key: 'tab', modifiers: ['meta'] },
    show_desktop: { key: 'd', modifiers: ['meta'] },
    prev_tab: { key: 'tab', modifiers: ['ctrl', 'shift'] },
    next_tab: { key: 'tab', modifiers: ['ctrl'] },
  },
  macos: {
    // Mission Control and Show Desktop default shortcuts.
    task_view: { key: 'up', modifiers: ['ctrl'] },
    show_desktop: { key: 'f11', modifiers: [] },
    prev_tab: { key: 'tab', modifiers: ['ctrl', 'shift'] },
    next_tab: { key: 'tab', modifiers: ['ctrl'] },
  },
  linux: {
    // GNOME overview (Super+S) and the common Super+D show-desktop shortcut.
    task_view: { key: 's', modifiers: ['meta'] },
    show_desktop: { key: 'd', modifiers: ['meta'] },
    prev_tab: { key: 'tab', modifiers: ['ctrl', 'shift'] },
    next_tab: { key: 'tab', modifiers: ['ctrl'] },
  },
}

export function comboFor(os: HostOs, action: ThreeFingerAction): KeyCombo | null {
  return action === 'none' ? null : THREE_FINGER_COMBOS[os][action]
}

export const THREE_FINGER_LABELS: Record<ThreeFingerAction, string> = {
  task_view: 'Task view',
  show_desktop: 'Show desktop',
  prev_tab: 'Previous tab',
  next_tab: 'Next tab',
  none: 'Nothing',
}
