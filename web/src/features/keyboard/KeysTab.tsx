import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  CornerDownLeft,
  Delete,
  Send,
  Space,
  type LucideIcon,
} from 'lucide-react'
import { useState, type SyntheticEvent } from 'react'
import { haptic } from '../../lib/haptics.ts'
import type { KeyName } from '../../lib/protocol.ts'
import { client, useConnection } from '../../store/remote.ts'
import { Button } from '../../ui/Button.tsx'
import { Card } from '../../ui/primitives.tsx'
import { FeatureGate } from '../FeatureGate.tsx'

const QUICK_KEYS: { key: KeyName; label: string; Icon?: LucideIcon }[] = [
  { key: 'esc', label: 'Esc' },
  { key: 'tab', label: 'Tab' },
  { key: 'backspace', label: 'Backspace', Icon: Delete },
  { key: 'enter', label: 'Enter', Icon: CornerDownLeft },
  { key: 'space', label: 'Space', Icon: Space },
  { key: 'f', label: 'F' },
]

const ARROWS: { key: KeyName; label: string; Icon: LucideIcon; area: string }[] = [
  { key: 'up', label: 'Up', Icon: ArrowUp, area: 'col-start-2' },
  { key: 'left', label: 'Left', Icon: ArrowLeft, area: 'col-start-1 row-start-2' },
  { key: 'down', label: 'Down', Icon: ArrowDown, area: 'col-start-2 row-start-2' },
  { key: 'right', label: 'Right', Icon: ArrowRight, area: 'col-start-3 row-start-2' },
]

function KeyButton({ k, label, Icon, className = '' }: { k: KeyName; label: string; Icon?: LucideIcon | undefined; className?: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      className={`flex min-h-14 items-center justify-center rounded-[var(--radius-control)] bg-[var(--color-surface-strong)] text-sm font-medium ring-1 ring-inset ring-[var(--color-line)] outline-none active:bg-[var(--color-line-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${className}`}
      onClick={() => {
        haptic('click')
        client.send('key.press', { key: k, modifiers: [] })
      }}
    >
      {Icon !== undefined ? <Icon className="h-5 w-5" aria-hidden="true" /> : label}
    </button>
  )
}

export function KeysTab() {
  const [text, setText] = useState('')
  const owner = useConnection((s) => s.session?.role === 'owner')

  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (text.length === 0) return
    client.send('key.text', { text })
    haptic('click')
    setText('')
  }

  return (
    <div className="flex flex-col gap-4 pt-2">
      <h1 className="text-2xl font-semibold">Keys</h1>
      {!owner ? (
        <Card>
          <p className="text-[var(--color-text-secondary)]">Only the owner can type on this laptop.</p>
        </Card>
      ) : (
        <FeatureGate feature="input" title="Typing">
          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium">Type on your laptop</span>
              <textarea
                value={text}
                maxLength={2000}
                rows={3}
                onChange={(e) => {
                  setText(e.target.value)
                }}
                placeholder="Text is typed where the cursor is"
                className="min-h-24 resize-none rounded-[var(--radius-control)] bg-[var(--color-surface)] px-4 py-3 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none placeholder:text-[var(--color-text-tertiary)] focus:ring-2 focus:ring-[var(--color-accent)]"
              />
            </label>
            <Button type="submit" variant="primary" size="lg" disabled={text.length === 0} icon={<Send className="h-5 w-5" aria-hidden="true" />}>
              Send
            </Button>
          </form>
          <div className="grid grid-cols-3 gap-2">
            {QUICK_KEYS.map((q) => (
              <KeyButton key={q.key} k={q.key} label={q.label} Icon={q.Icon} />
            ))}
          </div>
          <div className="mx-auto grid w-full max-w-64 grid-cols-3 grid-rows-2 gap-2">
            {ARROWS.map((a) => (
              <KeyButton key={a.key} k={a.key} label={a.label} Icon={a.Icon} className={a.area} />
            ))}
          </div>
        </FeatureGate>
      )}
    </div>
  )
}
