import { create } from 'zustand'
import type { Mode } from '../lib/adaptive.ts'
import type { Theme } from '../lib/color.ts'

export type TabId = 'now' | 'trackpad' | 'keys' | 'launch' | 'more'
export type MoreScreen = 'menu' | 'scenes' | 'timer' | 'power' | 'ai' | 'send' | 'layouts' | 'laptops' | 'devices' | 'settings'

export interface ToastItem {
  id: number
  level: 'info' | 'success' | 'warn' | 'error'
  message: string
}

/** 'auto' follows the artwork-first player layout unless auto-switch picked a mode. */
export type PlayerMode = 'auto' | Mode

interface UiState {
  tab: TabId
  mode: PlayerMode
  /** Context key of the last banner the person dismissed. */
  dismissedBanner: string | null
  autoSwitch: boolean
  /** Dark by default; the sun/moon button in the header switches to light. */
  theme: Theme
  toggleTheme: () => void
  /** Media controls on the phone's lock screen (on by default; starts after the first tap). */
  lockScreen: boolean
  setLockScreen: (on: boolean) => void
  /** Keys tab: typing, or the button layout for the app in front. */
  keysMode: 'type' | 'buttons'
  setKeysMode: (mode: 'type' | 'buttons') => void
  /** A layout picked by hand; null follows the app in front. */
  layoutPick: string | null
  setLayoutPick: (id: string | null) => void
  /** The sleep timer's last "when it ends" choice, reused next time. */
  timerThen: 'pause' | 'pause_lock' | 'pause_sleep'
  setTimerThen: (then: 'pause' | 'pause_lock' | 'pause_sleep') => void
  setMode: (mode: PlayerMode) => void
  dismissBanner: (key: string) => void
  setAutoSwitch: (on: boolean) => void
  /** -1 or 1: which way the last tab change went, for the slide animation. */
  direction: number
  more: MoreScreen
  toast: ToastItem | null
  setTab: (tab: TabId) => void
  setMore: (screen: MoreScreen) => void
  showToast: (level: ToastItem['level'], message: string) => void
  dismissToast: (id: number) => void
}

export const TAB_ORDER: TabId[] = ['now', 'trackpad', 'keys', 'launch', 'more']

const TAB_KEY = 'lapremote.tab'
const THEME_KEY = 'lapremote.theme'
const LOCK_KEY = 'lapremote.lockScreen'

function initialLockScreen(): boolean {
  try {
    return localStorage.getItem(LOCK_KEY) !== '0'
  } catch {
    return true
  }
}

function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

/** Apply the theme to the page: the CSS tokens, the browser bars and form controls. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  const bar = document.querySelector('meta[name="theme-color"]')
  bar?.setAttribute('content', theme === 'light' ? '#f4f5f9' : '#07070b')
  document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', theme)
}
const AUTO_SWITCH_KEY = 'lapremote.autoSwitch'

function initialAutoSwitch(): boolean {
  try {
    return localStorage.getItem(AUTO_SWITCH_KEY) === '1'
  } catch {
    return false
  }
}
const REPEAT_WINDOW_MS = 2000

function initialTab(): TabId {
  try {
    const saved = localStorage.getItem(TAB_KEY)
    return TAB_ORDER.includes(saved as TabId) ? (saved as TabId) : 'now'
  } catch {
    return 'now'
  }
}

let toastSeq = 0
let lastToast = { message: '', at: 0 }

export const useUi = create<UiState>((set, get) => ({
  tab: initialTab(),
  mode: 'auto',
  dismissedBanner: null,
  autoSwitch: initialAutoSwitch(),
  theme: initialTheme(),
  lockScreen: initialLockScreen(),
  setLockScreen: (on) => {
    try {
      localStorage.setItem(LOCK_KEY, on ? '1' : '0')
    } catch {
      // Not remembered across visits.
    }
    set({ lockScreen: on })
  },
  keysMode: 'type',
  setKeysMode: (keysMode) => {
    set({ keysMode })
  },
  layoutPick: null,
  setLayoutPick: (layoutPick) => {
    set({ layoutPick })
  },
  toggleTheme: () => {
    const theme: Theme = get().theme === 'dark' ? 'light' : 'dark'
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Not remembered across visits.
    }
    applyTheme(theme)
    set({ theme })
  },
  timerThen: 'pause',
  setTimerThen: (timerThen) => {
    set({ timerThen })
  },
  setMode: (mode) => {
    set({ mode })
  },
  dismissBanner: (key) => {
    set({ dismissedBanner: key })
  },
  setAutoSwitch: (on) => {
    try {
      localStorage.setItem(AUTO_SWITCH_KEY, on ? '1' : '0')
    } catch {
      // Not remembered across visits.
    }
    set({ autoSwitch: on })
  },
  direction: 1,
  more: 'menu',
  toast: null,
  setTab: (tab) => {
    const from = TAB_ORDER.indexOf(get().tab)
    const to = TAB_ORDER.indexOf(tab)
    try {
      localStorage.setItem(TAB_KEY, tab)
    } catch {
      // The tab simply won't be remembered.
    }
    set({ tab, direction: to >= from ? 1 : -1 })
  },
  setMore: (more) => {
    set({ more })
  },
  showToast: (level, message) => {
    const now = Date.now()
    if (lastToast.message === message && now - lastToast.at < REPEAT_WINDOW_MS) return
    lastToast = { message, at: now }
    toastSeq += 1
    set({ toast: { id: toastSeq, level, message } })
  },
  dismissToast: (id) => {
    if (get().toast?.id === id) set({ toast: null })
  },
}))

/** The tab to the left or right of `tab`, for swipe navigation. */
export function neighbourTab(tab: TabId, step: -1 | 1): TabId | null {
  const next = TAB_ORDER[TAB_ORDER.indexOf(tab) + step]
  return next ?? null
}
