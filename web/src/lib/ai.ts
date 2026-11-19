/**
 * Pure helpers for the AI screen: plain-language labels for planned actions and
 * suggestion chips that fit what the laptop is doing right now.
 */
import type { AgentPayload, AiAction, MediaSession, Shortcut } from './protocol.ts'

type Context = AgentPayload<'context.state'>

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function str(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function duration(seconds: number): string {
  const abs = Math.abs(seconds)
  if (abs >= 60 && abs % 60 === 0) return `${String(abs / 60)} min`
  if (abs >= 60) return `${String(Math.floor(abs / 60))}:${String(Math.round(abs % 60)).padStart(2, '0')}`
  return `${String(Math.round(abs))} s`
}

const THEN_LABELS: Record<string, string> = {
  pause: 'then pause',
  pause_lock: 'then pause and lock',
  pause_sleep: 'then pause and sleep',
}

const POWER_LABELS: Record<string, string> = {
  lock: 'Lock the laptop',
  sleep: 'Put the laptop to sleep',
  restart: 'Restart the laptop',
  shutdown: 'Shut down the laptop',
}

export interface Names {
  shortcut: (id: string) => string
  scene: (id: string) => string
  player: (id: string) => string
}

/** One short line describing a planned action, for the action chips. */
export function describeAction(action: AiAction, names: Names): string {
  const p = action.payload ?? {}
  const sessionId = str(p.sessionId)
  const on = sessionId !== null ? ` (${names.player(sessionId)})` : ''
  switch (action.type) {
    case 'media.toggle':
      return `Play or pause${on}`
    case 'media.play':
      return `Play${on}`
    case 'media.pause':
      return sessionId === null ? 'Pause everything' : `Pause${on}`
    case 'media.next':
      return `Next${on}`
    case 'media.prev':
      return `Previous${on}`
    case 'media.seek': {
      const by = num(p.by)
      const to = num(p.to)
      if (by !== null) return `${by < 0 ? 'Back' : 'Forward'} ${duration(by)}${on}`
      return `Jump to ${duration(to ?? 0)}${on}`
    }
    case 'media.select':
      return `Switch to ${names.player(sessionId ?? '')}`
    case 'volume.set':
      return `Volume ${String(num(p.level) ?? 0)}%`
    case 'volume.step': {
      const delta = num(p.delta) ?? 0
      return `Volume ${delta >= 0 ? 'up' : 'down'} ${String(Math.abs(delta))}`
    }
    case 'volume.mute':
      return p.muted === false ? 'Unmute' : 'Mute'
    case 'brightness.set':
      return `Brightness ${String(num(p.level) ?? 0)}%`
    case 'power.action':
      return POWER_LABELS[str(p.action) ?? ''] ?? 'Power'
    case 'launch.open':
      return `Open ${names.shortcut(str(p.shortcutId) ?? '')}`
    case 'scene.run':
      return `Run ${names.scene(str(p.sceneId) ?? '')}`
    case 'timer.set': {
      const then = THEN_LABELS[str(p.then) ?? ''] ?? ''
      if (p.mode === 'end_of_media') return `Sleep timer at the end of this, ${then}`
      return `Sleep timer ${duration((num(p.minutes) ?? 0) * 60)}, ${then}`
    }
    case 'timer.cancel':
      return 'Cancel the sleep timer'
    case 'key.press': {
      const mods = Array.isArray(p.modifiers) ? p.modifiers.filter((m): m is string => typeof m === 'string') : []
      const key = str(p.key) ?? ''
      const label = key.length === 1 ? key.toUpperCase() : key.charAt(0).toUpperCase() + key.slice(1)
      return `Press ${[...mods.map((m) => m.charAt(0).toUpperCase() + m.slice(1)), label].join('+')}`
    }
    case 'key.text': {
      const text = str(p.text) ?? ''
      return `Type "${text.length > 40 ? `${text.slice(0, 40)}...` : text}"`
    }
    case 'wait':
      return `Wait ${duration((num(p.ms) ?? 0) / 1000)}`
  }
}

/** Display names for ids in a plan, from what the phone already knows. */
export function namesFrom(shortcuts: Shortcut[] | null, scenes: { id: string; name: string }[] | null, sessions: MediaSession[]): Names {
  return {
    shortcut: (id) => shortcuts?.find((s) => s.id === id)?.name ?? id,
    scene: (id) => scenes?.find((s) => s.id === id)?.name ?? id,
    player: (id) => sessions.find((s) => s.id === id)?.appName ?? 'that player',
  }
}

const MAX_SUGGESTIONS = 4

/** Suggestion chips that fit the laptop right now. Never more than four. */
export function suggestions(context: Context | null, sessions: MediaSession[], shortcuts: Shortcut[] | null): string[] {
  const out: string[] = []
  const playing = sessions.some((s) => s.status === 'playing')
  const site = context?.site ?? null
  if (site === 'netflix' || site === 'prime') {
    out.push('Next episode', 'Go back 30 seconds')
  } else if (site === 'youtube') {
    out.push('Skip ahead 1 minute', 'Pause the video')
  } else if (context?.category === 'presentation') {
    out.push('Next slide')
  }
  if (playing) {
    out.push('Pause everything', 'Volume 30')
  } else if (shortcuts?.some((s) => s.id === 'youtube') === true) {
    out.push('Open YouTube and search lofi beats')
  }
  out.push('Sleep the laptop in 30 minutes')
  return [...new Set(out)].slice(0, MAX_SUGGESTIONS)
}
