import { Check, Loader2, Mic, MicOff, Send, ShieldAlert, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { describeAction, namesFrom, suggestions, type Names } from '../../lib/ai.ts'
import { useAi, type ChatEntry } from '../../store/ai.ts'
import { useExtras, useLaptopContext, useMedia } from '../../store/remote.ts'
import { Button, IconButton } from '../../ui/Button.tsx'
import { Card } from '../../ui/primitives.tsx'
import { Sheet } from '../../ui/Sheet.tsx'
import { isSecure } from '../../lib/secure.ts'

interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start: () => void
  stop: () => void
}
type RecognitionCtor = new () => Recognition

/** Web Speech is only offered on secure pages, and not by every browser. */
function speechCtor(): RecognitionCtor | null {
  if (!isSecure()) return null
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

function useSpeech(onText: (text: string, final: boolean) => void) {
  const ctor = useMemo(() => speechCtor(), [])
  const [listening, setListening] = useState(false)
  const rec = useRef<Recognition | null>(null)
  const latest = useRef(onText)
  useEffect(() => {
    latest.current = onText
  }, [onText])
  useEffect(
    () => () => {
      rec.current?.stop()
    },
    [],
  )
  const toggle = () => {
    if (ctor === null) return
    if (listening) {
      rec.current?.stop()
      return
    }
    const r = new ctor()
    r.lang = navigator.language
    r.interimResults = true
    r.continuous = false
    r.onresult = (e) => {
      const result = e.results[e.results.length - 1]
      if (result === undefined) return
      const text = Array.from({ length: result.length }, (_, i) => result[i]?.transcript ?? '').join('')
      latest.current(text, result.isFinal)
    }
    r.onend = () => {
      setListening(false)
    }
    r.onerror = () => {
      setListening(false)
    }
    rec.current = r
    setListening(true)
    r.start()
  }
  return { supported: ctor !== null, listening, toggle }
}

function StepChips({ entry, names }: { entry: ChatEntry; names: Names }) {
  const actions = entry.plan?.actions ?? []
  if (actions.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Steps">
      {actions.map((action, i) => {
        const step = entry.steps?.[i]
        const failed = step !== undefined && !step.ok
        const label = describeAction(action, names)
        return (
          <li
            key={`${action.type}-${String(i)}`}
            className={`inline-flex min-h-8 items-center gap-1.5 rounded-full px-3 text-xs ring-1 ring-inset ${
              failed
                ? 'bg-[var(--color-danger)]/10 text-[var(--color-danger)] ring-[var(--color-danger)]/40'
                : 'bg-[var(--color-bg-raised)] text-[var(--color-text-secondary)] ring-[var(--color-line)]'
            }`}
            title={step?.error ?? undefined}
          >
            {step?.ok === true && <Check className="h-3.5 w-3.5 text-[var(--color-success)]" aria-label="done" />}
            {failed && <X className="h-3.5 w-3.5" aria-label="failed" />}
            {step === undefined && entry.status === 'running' && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            <span>{label}</span>
            {failed && step.error != null && <span className="sr-only">: {step.error}</span>}
          </li>
        )
      })}
    </ul>
  )
}

function Bubble({ entry, names }: { entry: ChatEntry; names: Names }) {
  if (entry.role === 'you') {
    return (
      <div className="ml-10 self-end rounded-2xl rounded-br-md bg-[var(--color-accent)] px-4 py-2.5 text-[var(--color-accent-contrast)]">
        {entry.text}
      </div>
    )
  }
  const failedSteps = entry.steps?.filter((s) => !s.ok) ?? []
  return (
    <div className="mr-6 flex flex-col gap-2 self-start rounded-2xl rounded-bl-md bg-[var(--color-surface)] px-4 py-3 ring-1 ring-inset ring-[var(--color-line)]">
      {entry.status === 'thinking' ? (
        <p className="flex items-center gap-2 text-[var(--color-text-secondary)]" role="status">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Thinking...
        </p>
      ) : (
        <p className={entry.status === 'error' ? 'text-[var(--color-danger)]' : ''}>{entry.text}</p>
      )}
      <StepChips entry={entry} names={names} />
      {entry.status === 'waiting' && <p className="text-sm text-[var(--color-warn)]">Waiting for you to confirm.</p>}
      {entry.status === 'declined' && <p className="text-sm text-[var(--color-text-tertiary)]">Cancelled. Nothing was done.</p>}
      {failedSteps.length > 0 && (
        <p className="text-sm text-[var(--color-danger)]">
          {failedSteps.length === 1 ? 'One step' : `${String(failedSteps.length)} steps`} didn't work: {failedSteps[0]?.error}
        </p>
      )}
    </div>
  )
}

function ConfirmSheet({ entry, names }: { entry: ChatEntry | null; names: Names }) {
  const confirm = useAi((s) => s.confirm)
  const plan = entry?.plan
  return (
    <Sheet
      open={plan !== undefined}
      title="Do this on your laptop?"
      onClose={() => {
        if (plan !== undefined) void confirm(plan.planId, false)
      }}
    >
      {plan !== undefined && (
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-warn)]" aria-hidden="true" />
            <p className="text-sm text-[var(--color-text-secondary)]">{plan.reply}</p>
          </div>
          <ol className="flex list-decimal flex-col gap-1.5 pl-5">
            {plan.actions.map((a, i) => (
              <li key={`${a.type}-${String(i)}`}>{describeAction(a, names)}</li>
            ))}
          </ol>
          <div className="flex gap-3">
            <Button
              className="flex-1"
              size="lg"
              onClick={() => {
                void confirm(plan.planId, false)
              }}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              size="lg"
              variant="primary"
              onClick={() => {
                void confirm(plan.planId, true)
              }}
            >
              Do it
            </Button>
          </div>
        </div>
      )}
    </Sheet>
  )
}

export function AiScreen() {
  const entries = useAi((s) => s.entries)
  const busy = useAi((s) => s.busy)
  const ask = useAi((s) => s.ask)
  const { media } = useMedia()
  const context = useLaptopContext((s) => s.context)
  const shortcuts = useExtras((s) => s.shortcuts)
  const scenes = useExtras((s) => s.scenes)
  const sessions = media?.sessions ?? []
  const names = namesFrom(shortcuts, scenes, sessions)
  const chips = suggestions(context, sessions, shortcuts)
  const [text, setText] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const waiting = entries.find((e) => e.status === 'waiting') ?? null

  const submit = (value: string) => {
    if (value.trim() === '' || busy) return
    setText('')
    void ask(value)
  }
  const speech = useSpeech((heard, final) => {
    setText(heard)
    if (final) submit(heard)
  })

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [entries])

  return (
    <div className="flex flex-col gap-4">
      {entries.length === 0 ? (
        <Card className="flex flex-col gap-1">
          <p className="font-medium">Tell your laptop what to do.</p>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Like "pause everything" or "volume 30 and next episode". Anything risky asks you first.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3" aria-live="polite" aria-label="Conversation">
          {entries.map((e) => (
            <Bubble key={e.id} entry={e} names={names} />
          ))}
          <div ref={endRef} />
        </div>
      )}

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" data-no-swipe aria-label="Suggestions" role="group">
        {chips.map((chip) => (
          <button
            key={chip}
            type="button"
            disabled={busy}
            className="min-h-11 shrink-0 rounded-full bg-[var(--color-surface)] px-4 text-sm text-[var(--color-text-secondary)] ring-1 ring-inset ring-[var(--color-line)] disabled:opacity-40"
            onClick={() => {
              submit(chip)
            }}
          >
            {chip}
          </button>
        ))}
      </div>

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          submit(text)
        }}
      >
        <input
          value={text}
          maxLength={500}
          onChange={(e) => {
            setText(e.target.value)
          }}
          placeholder={speech.listening ? 'Listening...' : 'Ask your laptop'}
          aria-label="Ask your laptop"
          enterKeyHint="send"
          className="min-h-12 min-w-0 flex-1 rounded-full bg-[var(--color-surface)] px-4 ring-1 ring-inset ring-[var(--color-line-strong)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        />
        {speech.supported && (
          <IconButton label={speech.listening ? 'Stop listening' : 'Speak'} onClick={speech.toggle} disabled={busy}>
            {speech.listening ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </IconButton>
        )}
        <IconButton label="Send" variant="solid" type="submit" disabled={busy || text.trim() === ''}>
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
        </IconButton>
      </form>
      {!speech.supported && (
        <p className="text-sm text-[var(--color-text-tertiary)]">
          {isSecure()
            ? "To talk instead of typing, use the mic on your phone's keyboard."
            : "To talk instead of typing, use the mic on your phone's keyboard. A mic button appears here on HTTPS."}
        </p>
      )}
      <ConfirmSheet entry={waiting} names={names} />
    </div>
  )
}
