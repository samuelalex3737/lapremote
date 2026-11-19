import { useState, type SyntheticEvent } from 'react'
import type { PairError } from '../../lib/ws.ts'

const ERRORS: Record<PairError, string> = {
  invalid_code: "That code didn't work. Check the code on your laptop and try again.",
  expired_code: 'That code has expired. Your laptop is showing a new one.',
  rate_limited: 'Too many tries. Wait a minute, then try again.',
  bad_token: 'This phone was unpaired from your laptop. Pair it again.',
  revoked: 'This phone was removed from your laptop. Pair it again.',
}

interface Props {
  error: PairError | null
  busy: boolean
  onPair: (code: string) => void
}

export function PairScreen({ error, busy, onPair }: Props) {
  const [code, setCode] = useState('')
  const ready = /^\d{6}$/.test(code) && !busy

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (ready) onPair(code)
  }

  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-6" noValidate>
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Pair with your laptop</h1>
        <p className="text-base text-zinc-300">
          Scan the QR code shown on your laptop, or type the 6-digit code.
        </p>
      </div>
      <label className="flex flex-col gap-2 text-left">
        <span className="text-sm font-medium text-zinc-300">Pairing code</span>
        <input
          value={code}
          onChange={(e) => {
            setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
          }}
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="\d{6}"
          maxLength={6}
          aria-invalid={error !== null}
          aria-describedby={error !== null ? 'pair-error' : undefined}
          className="min-h-14 rounded-2xl border border-white/10 bg-white/5 px-4 text-center text-3xl font-semibold tracking-[0.4em] tabular-nums outline-none focus:border-white/40"
          placeholder="000000"
        />
      </label>
      {error !== null && (
        <p id="pair-error" role="alert" className="text-base text-rose-300">
          {ERRORS[error]}
        </p>
      )}
      <button
        type="submit"
        disabled={!ready}
        className="min-h-12 rounded-full bg-zinc-100 px-6 text-base font-semibold text-zinc-900 transition active:scale-95 disabled:opacity-40"
      >
        {busy ? 'Pairing...' : 'Pair'}
      </button>
    </form>
  )
}
