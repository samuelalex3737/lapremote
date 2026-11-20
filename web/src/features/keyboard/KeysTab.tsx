import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, CornerDownLeft, Delete, Send, Space, type LucideIcon } from 'lucide-react'
import { useRef, useState, type SyntheticEvent } from 'react'
import { haptic } from '../../lib/haptics.ts'
import { COMBO_KEYS, commonShortcuts, liveDiff, modifierLabel, type HostOs } from '../../lib/keys.ts'
import type { KeyName, Modifier } from '../../lib/protocol.ts'
import { client, useConnection } from '../../store/remote.ts'
import { Button } from '../../ui/Button.tsx'
import { Card, SegmentedControl } from '../../ui/primitives.tsx'
import { FeatureGate } from '../FeatureGate.tsx'
import { LayoutPad } from '../layouts/LayoutPad.tsx'
import { useUi } from '../../store/ui.ts'

function press(key: KeyName, modifiers: Modifier[] = []) {
  haptic('click')
  client.send('key.press', { key, modifiers })
}

const START: Record<HostOs, { label: string; key: KeyName; modifiers: Modifier[] }> = {
  windows: { label: 'Start', key: 'esc', modifiers: ['ctrl'] },
  macos: { label: 'Spotlight', key: 'space', modifiers: ['meta'] },
  linux: { label: 'Activities', key: 's', modifiers: ['meta'] },
}

const ARROWS: { key: KeyName; label: string; Icon: LucideIcon }[] = [
  { key: 'left', label: 'Left', Icon: ArrowLeft },
  { key: 'up', label: 'Up', Icon: ArrowUp },
  { key: 'down', label: 'Down', Icon: ArrowDown },
  { key: 'right', label: 'Right', Icon: ArrowRight },
]

// The keys come in three groups: stacked in portrait, side by side when the phone is sideways.
const GROUP = 'flex min-w-0 flex-col gap-2.5 short:gap-2 land:flex-1'

const keyClass =
  'flex min-h-11 min-w-11 items-center justify-center rounded-[var(--radius-control)] bg-[var(--color-surface-strong)] px-3 text-sm font-medium ring-1 ring-inset ring-[var(--color-line)] outline-none active:bg-[var(--color-line-strong)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]'

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
    <form onSubmit={submit} className="flex items-stretch gap-2 land:flex-col">
      <label className="flex min-w-0 flex-1">
        <span className="sr-only">Type, then send</span>
        <textarea
          value={text}
          maxLength={2000}
          rows={2}
          onChange={(e) => {
            setText(e.target.value)
          }}
          placeholder="Text is typed where the cursor is"
          className="min-h-14 w-full resize-none rounded-[var(--radius-control)] short:min-h-12 short:py-2 land:min-h-12 land:py-2 bg-[var(--color-surface)] px-4 py-2.5 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none placeholder:text-[var(--color-text-tertiary)] focus:ring-2 focus:ring-[var(--color-accent)]"
        />
      </label>
      <Button
        type="submit"
        variant="primary"
        className="shrink-0 rounded-[var(--radius-control)]"
        disabled={text.length === 0}
        icon={<Send className="h-5 w-5" aria-hidden="true" />}
      >
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
    <label className="flex flex-col">
      <span className="sr-only">Live typing</span>
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
        className="min-h-12 rounded-[var(--radius-control)] bg-[var(--color-surface)] px-4 text-base ring-1 ring-inset ring-[var(--color-line)] outline-none placeholder:text-[var(--color-text-tertiary)] focus:ring-2 focus:ring-[var(--color-accent)]"
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
    <Card className="flex flex-col gap-2 p-3 short:p-2.5 land:p-2.5">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)] short:sr-only land:sr-only">
        Key combo <span className="font-normal normal-case">- pick modifiers, then a key</span>
      </h2>
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
      <div className="-mx-3 flex gap-2 overflow-x-auto px-3" data-no-swipe aria-label="Then press">
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
    </Card>
  )
}

export function KeysTab() {
  const session = useConnection((s) => s.session)
  const [mode, setMode] = useState<'send' | 'live'>('send')
  const keysMode = useUi((s) => s.keysMode)
  const setKeysMode = useUi((s) => s.setKeysMode)
  if (session === null) return null
  const os = session.os
  const start = START[os]

  return (
    <div className="flex flex-col gap-2.5 pt-1 short:gap-2">
      <h1 className="sr-only">Keys</h1>
      {session.role !== 'owner' ? (
        <Card>
          <p className="text-[var(--color-text-secondary)]">Only the owner can type on this laptop.</p>
        </Card>
      ) : (
        <FeatureGate feature="input" title="Typing">
          <div className={keysMode === 'buttons' ? '' : 'land:hidden'}>
          <SegmentedControl
            label="Keys mode"
            options={[
              { value: 'send', label: 'Send' },
              { value: 'live', label: 'Live' },
              { value: 'buttons', label: 'Buttons' },
            ]}
            value={keysMode === 'buttons' ? 'buttons' : mode}
            onChange={(value) => {
              if (value === 'buttons') {
                setKeysMode('buttons')
                return
              }
              setMode(value)
              setKeysMode('type')
            }}
          />
          </div>
          {keysMode === 'buttons' ? (
            <LayoutPad />
          ) : (
          <div className="flex flex-col gap-2.5 short:gap-2 land:flex-row land:items-start land:gap-4">
            <div className={GROUP}>
              <div className="hidden land:block">
              <SegmentedControl
                label="Keys mode"
                options={[
                  { value: 'send', label: 'Send' },
                  { value: 'live', label: 'Live' },
                  { value: 'buttons', label: 'Buttons' },
                ]}
                value={mode}
                onChange={(value) => {
                  if (value === 'buttons') {
                    setKeysMode('buttons')
                    return
                  }
                  setMode(value)
                  setKeysMode('type')
                }}
              />
              </div>
              {mode === 'send' ? <SendBox /> : <LiveBox />}
            </div>
            <div className={GROUP}>
              <div className="grid grid-cols-4 gap-2">
                <KeyButton k="esc" label="Esc" />
                <KeyButton k="tab" label="Tab" />
                <KeyButton k="backspace" label="Backspace" Icon={Delete} />
                <KeyButton k="enter" label="Enter" Icon={CornerDownLeft} />
                <KeyButton k="space" label="Space" Icon={Space} className="col-span-2" />
                <KeyButton k="f" label="F" />
                <KeyButton k={start.key} label={start.label} modifiers={start.modifiers} />
              </div>
              <div className="grid grid-cols-4 gap-2">
                {ARROWS.map((a) => (
                  <KeyButton key={a.key} k={a.key} label={a.label} Icon={a.Icon} />
                ))}
              </div>
            </div>
            <div className={GROUP}>
              {/* Two rows of shortcuts, or one scrolling row when the screen is short. */}
              <div className="grid grid-cols-3 gap-2 short:-mx-4 short:flex short:overflow-x-auto short:px-4" data-no-swipe>
                {commonShortcuts(os).map((c) => (
                  <KeyButton key={c.label} k={c.key} label={c.label} modifiers={c.modifiers} className="short:shrink-0" />
                ))}
              </div>
              <ComboBuilder os={os} />
            </div>
          </div>
          )}
        </FeatureGate>
      )}
    </div>
  )
}
