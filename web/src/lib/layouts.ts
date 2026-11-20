/**
 * Per-app button layouts: which one fits the app in front, and what a button sends.
 * A button only ever sends an existing, allowlisted message, so the laptop checks it
 * exactly like the phone's own buttons.
 */
import type { ContextInfo } from './adaptive.ts'
import type { ButtonAction, ClientPayload, ClientType, Layout } from './protocol.ts'

/** The first layout whose process names, sites or title fragments fit the app in front. */
export function matchLayout(layouts: readonly Layout[] | null, context: ContextInfo | null): Layout | null {
  if (layouts === null || context === null) return null
  const process = context.processName.toLowerCase()
  const title = context.windowTitle.toLowerCase()
  for (const layout of layouts) {
    const m = layout.match
    if (m === undefined) continue
    if ((m.processes ?? []).some((p) => p.toLowerCase() === process)) return layout
    if (context.site !== null && (m.sites ?? []).includes(context.site)) return layout
    if ((m.titles ?? []).some((t) => title.includes(t.toLowerCase()))) return layout
  }
  return null
}

/** Layouts worth offering in the header when their app comes to the front. */
export const CALL_LAYOUTS = new Set(['zoom', 'teams', 'meet'])

export interface Outgoing<T extends ClientType = ClientType> {
  type: T
  payload: ClientPayload<T>
}

/** The message a layout button sends. */
export function buttonMessage(action: ButtonAction): Outgoing {
  switch (action.type) {
    case 'key':
      return { type: 'key.press', payload: { key: action.key, modifiers: action.modifiers ?? [] } }
    case 'media':
      return { type: `media.${action.command}`, payload: {} }
    case 'seek':
      return { type: 'media.seek', payload: { by: action.by } }
    case 'volume':
      return { type: 'volume.step', payload: { delta: action.delta } }
    case 'launch':
      return { type: 'launch.open', payload: { shortcutId: action.shortcutId } }
  }
}

const MOD_LABEL: Record<string, Record<string, string>> = {
  macos: { ctrl: 'Ctrl', alt: 'Option', shift: 'Shift', meta: 'Cmd' },
  windows: { ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', meta: 'Win' },
  linux: { ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', meta: 'Super' },
}

/** "Ctrl+Shift+M", "Play / pause", "Back 10s": a short description for editors. */
export function describeAction(action: ButtonAction, os: string, shortcutName: (id: string) => string): string {
  switch (action.type) {
    case 'key': {
      const labels = MOD_LABEL[os] ?? MOD_LABEL.windows ?? {}
      const key = action.key.length === 1 ? action.key.toUpperCase() : action.key.charAt(0).toUpperCase() + action.key.slice(1)
      return [...(action.modifiers ?? []).map((m) => labels[m] ?? m), key].join('+')
    }
    case 'media':
      return { toggle: 'Play / pause', play: 'Play', pause: 'Pause', next: 'Next', prev: 'Previous' }[action.command]
    case 'seek':
      return `${action.by < 0 ? 'Back' : 'Forward'} ${String(Math.abs(action.by))}s`
    case 'volume':
      return `Volume ${action.delta < 0 ? 'down' : 'up'} ${String(Math.abs(action.delta))}`
    case 'launch':
      return `Open ${shortcutName(action.shortcutId)}`
  }
}

/** A new layout id from its name, unique among the existing ones. */
export function layoutId(name: string, existing: readonly Layout[]): string {
  const base =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40) || 'layout'
  const taken = new Set(existing.map((l) => l.id))
  if (!taken.has(base)) return base
  for (let i = 2; ; i += 1) {
    const candidate = `${base}-${String(i)}`
    if (!taken.has(candidate)) return candidate
  }
}

/** Comma-separated text from an editor field to a clean list. */
export function splitList(value: string, min = 1, max = 64): string[] {
  return value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length >= min && s.length <= max)
    .slice(0, 10)
}
