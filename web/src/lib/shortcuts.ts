import type { Shortcut } from './protocol.ts'

/** Shortcuts whose id starts with "_" are internal (the "open once" slot) and never shown. */
export function visibleShortcuts(shortcuts: Shortcut[] | null): Shortcut[] {
  return (shortcuts ?? []).filter((s) => !s.id.startsWith('_'))
}

/** A stable, protocol-safe id from a name, unique among `taken`. */
export function makeId(name: string, taken: readonly string[]): string {
  const base =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40) || 'item'
  let id = base
  for (let n = 2; taken.includes(id); n += 1) id = `${base}-${String(n)}`
  return id
}

/** Accepts "netflix.com" and adds https://; anything else than http(s) is refused. */
export function normaliseUrl(input: string): string | null {
  const value = input.trim()
  if (value === '') return null
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(value) ? value : `https://${value}`
  try {
    const url = new URL(withScheme)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    if (!url.hostname.includes('.') && url.hostname !== 'localhost') return null
    return url.toString()
  } catch {
    return null
  }
}

export const ONCE_ID = '_once'
