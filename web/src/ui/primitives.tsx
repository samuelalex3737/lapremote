import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { haptic } from '../lib/haptics.ts'
import { springs } from './motion.ts'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-[var(--radius-card)] bg-[var(--color-surface)] p-4 ring-1 ring-inset ring-[var(--color-line)] ${className}`}
    >
      {children}
    </section>
  )
}

export function Skeleton({ className = '', label }: { className?: string; label: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className={`animate-pulse rounded-[var(--radius-card)] bg-[var(--color-surface-strong)] ${className}`}
    />
  )
}

export function EmptyState(props: { icon: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[var(--radius-card)] bg-[var(--color-surface)] px-6 py-10 text-center ring-1 ring-inset ring-[var(--color-line)]">
      <span className="text-[var(--color-text-secondary)]" aria-hidden="true">
        {props.icon}
      </span>
      <p className="text-lg font-semibold">{props.title}</p>
      {props.body !== undefined && (
        <p className="max-w-xs text-sm text-[var(--color-text-secondary)]">{props.body}</p>
      )}
      {props.action}
    </div>
  )
}

export function Switch(props: { label: string; checked: boolean; onChange: (checked: boolean) => void; description?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={props.checked}
      className="flex min-h-14 w-full items-center justify-between gap-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
      onClick={() => {
        haptic('tick')
        props.onChange(!props.checked)
      }}
    >
      <span className="flex flex-col">
        <span className="text-base font-medium">{props.label}</span>
        {props.description !== undefined && (
          <span className="text-sm text-[var(--color-text-secondary)]">{props.description}</span>
        )}
      </span>
      <span
        className={`relative inline-flex h-8 w-[52px] shrink-0 rounded-full transition-colors ${
          props.checked ? 'bg-[var(--color-success)]' : 'bg-[var(--color-surface-strong)] ring-1 ring-inset ring-[var(--color-line-strong)]'
        }`}
      >
        <motion.span
          layout
          transition={springs.snappy}
          className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow ${props.checked ? 'right-1' : 'left-1'}`}
        />
      </span>
    </button>
  )
}

export function SegmentedControl<T extends string>(props: {
  label: string
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label={props.label}
      className="relative flex rounded-full bg-[var(--color-surface-strong)] p-1 ring-1 ring-inset ring-[var(--color-line)]"
    >
      {props.options.map((option) => {
        const active = option.value === props.value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            className="relative z-10 min-h-11 flex-1 rounded-full px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            onClick={() => {
              haptic('tick')
              props.onChange(option.value)
            }}
          >
            {active && (
              <motion.span
                layoutId={`seg-${props.label}`}
                transition={springs.snappy}
                className="absolute inset-0 -z-10 rounded-full bg-[var(--color-text)]"
              />
            )}
            <span className={active ? 'text-[var(--color-bg)]' : 'text-[var(--color-text-secondary)]'}>
              {option.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}

export function ListRow(props: {
  icon?: ReactNode
  title: string
  subtitle?: string
  trailing?: ReactNode
  onClick?: () => void
  disabled?: boolean
}) {
  const content = (
    <>
      {props.icon !== undefined && (
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-surface-strong)]" aria-hidden="true">
          {props.icon}
        </span>
      )}
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-base font-medium">{props.title}</span>
        {props.subtitle !== undefined && (
          <span className="truncate text-sm text-[var(--color-text-secondary)]">{props.subtitle}</span>
        )}
      </span>
      {props.trailing}
    </>
  )
  const className = 'flex min-h-16 w-full items-center gap-3 px-4 py-2 text-left'
  if (props.onClick === undefined) return <div className={className}>{content}</div>
  return (
    <button
      type="button"
      disabled={props.disabled}
      className={`${className} outline-none active:bg-[var(--color-surface)] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-accent)] disabled:opacity-50`}
      onClick={() => {
        haptic('tick')
        props.onClick?.()
      }}
    >
      {content}
    </button>
  )
}

export function StatusPill(props: { tone: 'ok' | 'warn' | 'off'; children: ReactNode }) {
  const tones = {
    ok: 'bg-[var(--color-success)]/12 text-[var(--color-success)] ring-[var(--color-success)]/30',
    warn: 'bg-[var(--color-warn)]/12 text-[var(--color-warn)] ring-[var(--color-warn)]/30',
    off: 'bg-[var(--color-surface-strong)] text-[var(--color-text-secondary)] ring-[var(--color-line)]',
  } as const
  return (
    <p
      role="status"
      className={`inline-flex max-w-full items-center gap-2 truncate rounded-full px-3 py-1.5 text-xs font-medium ring-1 ring-inset ${tones[props.tone]}`}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 shrink-0 rounded-full ${props.tone === 'ok' ? 'bg-[var(--color-success)]' : props.tone === 'warn' ? 'bg-[var(--color-warn)]' : 'bg-[var(--color-text-tertiary)]'}`}
      />
      <span className="truncate">{props.children}</span>
    </p>
  )
}
