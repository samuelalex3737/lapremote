import { motion, type HTMLMotionProps } from 'motion/react'
import type { ReactNode } from 'react'
import { haptic } from '../lib/haptics.ts'
import { springs } from './motion.ts'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-[var(--color-accent)] text-[var(--color-accent-contrast)] font-semibold',
  secondary: 'bg-[var(--color-surface-strong)] text-[var(--color-text)] ring-1 ring-inset ring-[var(--color-line)]',
  ghost: 'bg-transparent text-[var(--color-text)]',
  danger: 'bg-[var(--color-danger)]/15 text-[var(--color-danger)] ring-1 ring-inset ring-[var(--color-danger)]/40',
}

export interface ButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
  variant?: Variant
  size?: 'md' | 'lg'
  icon?: ReactNode
  children?: ReactNode
  /** Skip the tap haptic (for buttons that trigger their own). */
  silent?: boolean
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  children,
  className = '',
  silent = false,
  onClick,
  type = 'button',
  ...rest
}: ButtonProps) {
  const sizing = size === 'lg' ? 'min-h-14 px-6 text-base' : 'min-h-11 px-4 text-sm'
  return (
    <motion.button
      type={type}
      whileTap={{ scale: 0.96 }}
      transition={springs.snappy}
      className={`inline-flex items-center justify-center gap-2 rounded-[var(--radius-pill)] font-medium outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-40 ${sizing} ${VARIANTS[variant]} ${className}`}
      onClick={(e) => {
        if (!silent) haptic('tick')
        onClick?.(e)
      }}
      {...rest}
    >
      {icon}
      {children}
    </motion.button>
  )
}

export interface IconButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
  label: string
  children: ReactNode
  size?: 'md' | 'lg' | 'xl'
  variant?: 'glass' | 'solid' | 'plain'
}

const ICON_SIZES = { md: 'h-11 w-11', lg: 'h-14 w-14', xl: 'h-20 w-20' } as const
const ICON_VARIANTS = {
  glass: 'bg-[var(--color-surface-strong)] ring-1 ring-inset ring-[var(--color-line)]',
  solid: 'bg-[var(--color-text)] text-[var(--color-bg)]',
  plain: 'bg-transparent',
} as const

export function IconButton({
  label,
  children,
  size = 'md',
  variant = 'glass',
  className = '',
  onClick,
  ...rest
}: IconButtonProps) {
  return (
    <motion.button
      type="button"
      aria-label={label}
      title={label}
      whileTap={{ scale: 0.9 }}
      transition={springs.snappy}
      className={`inline-flex shrink-0 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-35 ${ICON_SIZES[size]} ${ICON_VARIANTS[variant]} ${className}`}
      onClick={(e) => {
        haptic('tick')
        onClick?.(e)
      }}
      {...rest}
    >
      {children}
    </motion.button>
  )
}
