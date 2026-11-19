import { useEffect, useRef, useState } from 'react'
import type { RemoteClient } from '../lib/ws.ts'

interface ToastItem {
  id: number
  level: 'info' | 'success' | 'warn' | 'error'
  message: string
}

const SHOW_MS = 3500
const REPEAT_WINDOW_MS = 2000

const LEVEL_STYLE: Record<ToastItem['level'], string> = {
  info: 'border-white/15 bg-zinc-900/95 text-zinc-100',
  success: 'border-emerald-400/30 bg-emerald-950/95 text-emerald-100',
  warn: 'border-amber-400/30 bg-amber-950/95 text-amber-100',
  error: 'border-rose-400/30 bg-rose-950/95 text-rose-100',
}

/** Agent toasts plus failed acks, one at a time, never repeating the same text back to back. */
export function Toaster({ client }: { client: RemoteClient }) {
  const [toast, setToast] = useState<ToastItem | null>(null)
  const last = useRef<{ message: string; at: number }>({ message: '', at: 0 })
  const seq = useRef(0)

  useEffect(() => {
    const show = (level: ToastItem['level'], message: string) => {
      const now = Date.now()
      if (last.current.message === message && now - last.current.at < REPEAT_WINDOW_MS) return
      last.current = { message, at: now }
      seq.current += 1
      setToast({ id: seq.current, level, message })
    }
    const offToast = client.on('toast', (p) => {
      show(p.level, p.message)
    })
    const offAck = client.on('ack', (p) => {
      if (!p.ok && p.error != null) show('error', p.error)
    })
    return () => {
      offToast()
      offAck()
    }
  }, [client])

  useEffect(() => {
    if (toast === null) return
    const timer = setTimeout(() => {
      setToast((current) => (current?.id === toast.id ? null : current))
    }, SHOW_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [toast])

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 z-30 flex justify-center px-4"
      style={{ top: 'max(0.75rem, env(safe-area-inset-top))' }}
    >
      {toast !== null && (
        <p
          key={toast.id}
          className={`max-w-md rounded-2xl border px-4 py-3 text-sm shadow-lg ${LEVEL_STYLE[toast.level]}`}
        >
          {toast.message}
        </p>
      )}
    </div>
  )
}
