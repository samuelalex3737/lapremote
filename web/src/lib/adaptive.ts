/**
 * Context-aware suggestions: which control surface fits what is in front on the laptop,
 * and which site keys exist for movie controls.
 */
import type { AgentPayload, KeyName } from './protocol.ts'

export type ContextInfo = AgentPayload<'context.state'>
export type Mode = 'music' | 'movie' | 'presentation'

export interface Suggestion {
  mode: Mode
  /** Banner text, for example "Netflix in focus - movie controls". */
  text: string
  /** Identifies this context so a dismissed banner stays dismissed until focus changes. */
  key: string
}

const SITE_NAMES = {
  youtube: 'YouTube',
  netflix: 'Netflix',
  prime: 'Prime Video',
  spotify_web: 'Spotify',
  generic: null,
} as const

const VIDEO_SITES = new Set(['youtube', 'netflix', 'prime'])

export function suggestMode(context: ContextInfo | null): Suggestion | null {
  if (context === null) return null
  const key = `${context.processName}|${context.category}|${context.site ?? ''}`
  if (context.category === 'presentation') {
    return { mode: 'presentation', text: `${context.app} in focus - presentation controls`, key }
  }
  if (context.category === 'video') {
    return { mode: 'movie', text: `${context.app} in focus - movie controls`, key }
  }
  if (context.category === 'music') {
    return { mode: 'music', text: `${context.app} in focus - music controls`, key }
  }
  if (context.category === 'browser' && context.site !== null) {
    const name = SITE_NAMES[context.site]
    if (context.site === 'spotify_web') return { mode: 'music', text: 'Spotify in focus - music controls', key }
    if (VIDEO_SITES.has(context.site) && name !== null) {
      return { mode: 'movie', text: `${name} in focus - movie controls`, key }
    }
  }
  return null
}

export interface MovieKeys {
  fullscreen: KeyName
  /** Only where the site has a real keyboard shortcut; otherwise the button is hidden. */
  skipIntro: KeyName | null
  subtitles: KeyName | null
}

export function movieKeys(context: ContextInfo | null): MovieKeys {
  const site = context?.category === 'browser' ? context.site : null
  return {
    fullscreen: 'f',
    skipIntro: site === 'netflix' ? 's' : null,
    subtitles: site === 'youtube' ? 'c' : null,
  }
}

export const PRESENTATION_KEYS = { next: 'right', previous: 'left', blank: 'b' } as const satisfies Record<string, KeyName>
