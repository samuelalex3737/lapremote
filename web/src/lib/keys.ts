/**
 * Keyboard helpers: OS-aware common shortcuts and the diff that turns "live typing"
 * in a text field into key.text / backspace presses.
 */
import type { KeyName, Modifier } from './protocol.ts'

export type HostOs = 'windows' | 'macos' | 'linux'

export interface Combo {
  label: string
  key: KeyName
  modifiers: Modifier[]
}

/** Copy, paste, undo, close tab, new tab and app switching, with Cmd on macOS. */
export function commonShortcuts(os: HostOs): Combo[] {
  const primary: Modifier = os === 'macos' ? 'meta' : 'ctrl'
  return [
    { label: 'Copy', key: 'c', modifiers: [primary] },
    { label: 'Paste', key: 'v', modifiers: [primary] },
    { label: 'Undo', key: 'z', modifiers: [primary] },
    { label: 'Close tab', key: 'w', modifiers: [primary] },
    { label: 'New tab', key: 't', modifiers: [primary] },
    { label: os === 'macos' ? 'Cmd+Tab' : 'Alt+Tab', key: 'tab', modifiers: [os === 'macos' ? 'meta' : 'alt'] },
  ]
}

export function modifierLabel(m: Modifier, os: HostOs): string {
  if (m === 'meta') return os === 'macos' ? 'Cmd' : os === 'windows' ? 'Win' : 'Super'
  if (m === 'alt') return os === 'macos' ? 'Option' : 'Alt'
  return m === 'ctrl' ? 'Ctrl' : 'Shift'
}

export type LiveEdit = { kind: 'text'; text: string } | { kind: 'backspace'; count: number }

/**
 * What to send when a live-typing field changes from `before` to `after`:
 * deleted characters become backspaces, appended characters become text.
 * Edits in the middle are treated as delete-to-the-change then retype.
 */
export function liveDiff(before: string, after: string): LiveEdit[] {
  let common = 0
  const limit = Math.min(before.length, after.length)
  while (common < limit && before[common] === after[common]) common += 1
  const edits: LiveEdit[] = []
  const removed = before.length - common
  if (removed > 0) edits.push({ kind: 'backspace', count: removed })
  const added = after.slice(common)
  if (added.length > 0) edits.push({ kind: 'text', text: added })
  return edits
}

/** Keys offered in the combo builder after the modifiers are chosen. */
export const COMBO_KEYS: KeyName[] = [
  ...('abcdefghijklmnopqrstuvwxyz'.split('')),
  ...('0123456789'.split('')),
  'tab',
  'enter',
  'esc',
  'space',
  'backspace',
  'delete',
  'up',
  'down',
  'left',
  'right',
  'home',
  'end',
  'pageup',
  'pagedown',
  'f1',
  'f2',
  'f3',
  'f4',
  'f5',
  'f11',
  'f12',
]
