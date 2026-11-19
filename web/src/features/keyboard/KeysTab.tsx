import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, CornerDownLeft, Delete, Send, Space, type LucideIcon } from 'lucide-react'
import { useRef, useState, type SyntheticEvent } from 'react'
import { haptic } from '../../lib/haptics.ts'
import { COMBO_KEYS, commonShortcuts, liveDiff, modifierLabel, type HostOs } from '../../lib/keys.ts'
import type { KeyName, Modifier } from '../../lib/protocol.ts'
import { client, useConnection } from '../../store/remote.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, SegmentedControl } from '../../ui/primitives.tsx'
import { FeatureGate } from '../FeatureGate.tsx'

function press(key: KeyName, modifiers: Modifier[] = []) {
  haptic('click')
  client.send('key.press', { key, modifiers })
}

const START: Record<HostOs, { label: string; key: KeyName; modifiers: Modifier[] }> = {
  windows: { label: 'Start', key: 'esc', modifiers: ['ctrl'] },
  macos: { label: 'Spotlight', key: 'space', modifiers: ['meta'] },
  linux: { label: 'Activities', key: 's', modifiers: ['meta'] },
}

const ARROWS: { key: KeyName; label: string; Icon: LucideIcon; area: string }[] = [
  { key: 'up', label: 'Up', Icon: ArrowUp, area: 'col-start-2' },
  { key: 'left', label: 'Left', Icon: ArrowLeft, area: 'col-start-1 row-start-2' },
  { key: 'down', label: 'Down', Icon: ArrowDown, area: 'col-start-2 row-start-2' },
  { key: 'right', label: 'Right', Icon: ArrowRight, area: 'col-start-3 row-start-2' },
]

const keyClass =
  'flex min-h-12 min-w-12 items-center justify-center rounded-[var(--radius-control)] bg-[var(--color-surface-strong)] px-3 text-sm font-medium ring-1 ring-inset ring-[var(--color-line)] outline-none active:bg-[var(--color-line-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]'

function KeyButton(props: { k: KeyName; label: string; Icon?: LucideIcon | undefined; modifiers?: Modifier[]; className?: string }) {
  const Icon = props.Icon
  return (
    <button
      type="button"
      aria-label={props.label}
      className={`${keyClass} ${props.className ?? ''}`}
      onClick={() => {
        press(props.k, props.modifiers ?? [])
      }}
    >
      {Icon !== undefined ? <Icon className="h-5 w-5" aria-hidden="true" /> : props.label}
    </button>
  )
}

function SendBox() {
  const [text, setText] = useState('')
  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (text.length === 0) return
    client.send('key.text', { text })
    haptic('click')
    setText('')
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium">Type, then send</span>
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
  )
}

/** Every keystroke goes straight to the laptop. */
function LiveBox() {
  const [text, setText] = useState('')
  const previous = useRef('')
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm font-medium">Live typing</span>
      <input
        value={text}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        placeholder="Start typing"
        onChange={(e) => {
          const next = e.target.value
          for (const edit of liveDiff(previous.current, next)) {
            if (edit.kind === 'text') client.send('key.text', { text: edit.text })
            else for (let i = 0; i < edit.count; i += 1) client.send('key.press', { key: 'backspace', modifiers: [] })
          }
          previous.current = next
          setText(next)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            press('enter')
            previous.current = ''
            setText('')
          } else if (e.key === 'Backspace' && text.length === 0) {
            press('backspace')
          }
        }}
        className="min-h-14 rounded-[var(--radius-control)] bg-[var(--color-surface)] px-4 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none placeholder:text-[var(--color-text-tertiary)] focus:ring-2 focus:ring-[var(--color-accent)]"
      />
    </label>
  )
}

function ComboBuilder({ os }: { os: HostOs }) {
  const [mods, setMods] = useState<Modifier[]>([])
  const toggle = (m: Modifier) => {
    haptic('tick')
    setMods((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]))
  }
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Key combo</h2>
      <div className="flex gap-2" role="group" aria-label="Modifiers">
        {(['ctrl', 'alt', 'shift', 'meta'] as const).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={mods.includes(m)}
            className={`${keyClass} flex-1 ${mods.includes(m) ? 'bg-[var(--color-text)] text-[var(--color-bg)]' : ''}`}
            onClick={() => {
              toggle(m)
            }}
          >
            {modifierLabel(m, os)}
          </button>
        ))}
      </div>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" data-no-swipe aria-label="Then press">
        {COMBO_KEYS.map((k) => (
          <button
            key={k}
            type="button"
            className={`${keyClass} shrink-0 uppercase`}
            onClick={() => {
              press(k, mods)
              setMods([])
            }}
          >
            {k}
          </button>
        ))}
      </div>
      <p className="text-xs text-[var(--color-text-secondary)]">Pick modifiers, then tap a key.</p>
    </Card>
  )
}

export function KeysTab() {
  const session = useConnection((s) => s.session)
  const [mode, setMode] = useState<'send' | 'live'>('send')
  if (session === null) return null
  const os = session.os
  const start = START[os]

  return (
    <div className="flex flex-col gap-4 pt-2">
      <h1 className="text-2xl font-semibold">Keys</h1>
      {session.role !== 'owner' ? (
        <Card>
          <p className="text-[var(--color-text-secondary)]">Only the owner can type on this laptop.</p>
        </Card>
      ) : (
        <FeatureGate feature="input" title="Typing">
          <SegmentedControl
            label="Typing mode"
            options={[
              { value: 'send', label: 'Send' },
              { value: 'live', label: 'Live' },
            ]}
            value={mode}
            onChange={setMode}
          />
          {mode === 'send' ? <SendBox /> : <LiveBox />}
          <div className="grid grid-cols-4 gap-2">
            <KeyButton k="esc" label="Esc" />
            <KeyButton k="tab" label="Tab" />
            <KeyButton k="backspace" label="Backspace" Icon={Delete} />
            <KeyButton k="enter" label="Enter" Icon={CornerDownLeft} />
            <KeyButton k="space" label="Space" Icon={Space} className="col-span-2" />
            <KeyButton k="f" label="F" />
            <KeyButton k={start.key} label={start.label} modifiers={start.modifiers} />
          </div>
          <div className="mx-auto grid w-full max-w-64 grid-cols-3 grid-rows-2 gap-2">
            {ARROWS.map((a) => (
              <KeyButton key={a.key} k={a.key} label={a.label} Icon={a.Icon} className={a.area} />
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2">
            {commonShortcuts(os).map((c) => (
              <KeyButton key={c.label} k={c.key} label={c.label} modifiers={c.modifiers} />
            ))}
          </div>
          <ComboBuilder os={os} />
        </FeatureGate>
      )}
    </div>
  )
}
