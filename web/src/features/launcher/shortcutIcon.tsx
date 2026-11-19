import { AppWindow, Clapperboard, Globe, Music2, Play, Tv } from 'lucide-react'
import type { Shortcut } from '../../lib/protocol.ts'

const TONES: Record<string, string> = {
  netflix: 'bg-[#e50914]/20 text-[#ff6b74]',
  youtube: 'bg-[#ff0033]/20 text-[#ff6b7f]',
  music: 'bg-[#ff4e45]/20 text-[#ff8a84]',
  prime: 'bg-[#00a8e1]/20 text-[#5fd0f5]',
  spotify: 'bg-[#1db954]/20 text-[#5fe08c]',
}

export function ShortcutIcon({ shortcut }: { shortcut: Shortcut }) {
  const icon = shortcut.icon ?? (shortcut.kind === 'app' ? 'app' : 'web')
  const tone = TONES[icon] ?? 'bg-[var(--color-surface-strong)] text-[var(--color-text)]'
  const props = { className: 'h-6 w-6', 'aria-hidden': true } as const
  return (
    <span className={`flex h-12 w-12 items-center justify-center rounded-2xl ${tone}`}>
      {icon === 'netflix' ? (
        <Clapperboard {...props} />
      ) : icon === 'youtube' ? (
        <Play {...props} />
      ) : icon === 'music' || icon === 'spotify' ? (
        <Music2 {...props} />
      ) : icon === 'prime' ? (
        <Tv {...props} />
      ) : icon === 'app' ? (
        <AppWindow {...props} />
      ) : (
        <Globe {...props} />
      )}
    </span>
  )
}
