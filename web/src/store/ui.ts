import { create } from 'zustand'
import type { Mode } from '../lib/adaptive.ts'

export type TabId = 'now' | 'trackpad' | 'keys' | 'launch' | 'more'
export type MoreScreen = 'menu' | 'scenes' | 'timer' | 'power' | 'ai' | 'devices' | 'settings'

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
