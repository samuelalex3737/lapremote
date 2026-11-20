import { Moon, Sun } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense, useEffect, useRef, type ReactNode } from 'react'
import { Backdrop } from '../features/nowplaying/Backdrop.tsx'
import { NowPlayingTab } from '../features/nowplaying/NowPlayingTab.tsx'
import { useConnection, useIncoming } from '../store/remote.ts'
import { neighbourTab, useUi, type TabId } from '../store/ui.ts'
import { copyToPhone } from '../lib/copy.ts'
import { Button, IconButton } from '../ui/Button.tsx'
import { Sheet } from '../ui/Sheet.tsx'
import { Skeleton, StatusPill } from '../ui/primitives.tsx'
import { ContextBanner } from './ContextBanner.tsx'
import { useContextSuggestion } from './useContextSuggestion.ts'
import { useLockScreen } from './useLockScreen.ts'
import { TabBar } from './TabBar.tsx'

const SWIPE_MIN_PX = 70
const SWIPE_MAX_MS = 500

// Now Playing ships in the main bundle; the other tabs load on demand and are
// prefetched once the app is idle, so switching tabs stays instant.
const loadTrackpad = () => import('../features/trackpad/TrackpadTab.tsx')
const loadKeys = () => import('../features/keyboard/KeysTab.tsx')
const loadLaunch = () => import('../features/launcher/LaunchTab.tsx')
const loadMore = () => import('../features/more/MoreTab.tsx')
const TrackpadTab = lazy(() => loadTrackpad().then((m) => ({ default: m.TrackpadTab })))
const KeysTab = lazy(() => loadKeys().then((m) => ({ default: m.KeysTab })))
const LaunchTab = lazy(() => loadLaunch().then((m) => ({ default: m.LaunchTab })))
const MoreTab = lazy(() => loadMore().then((m) => ({ default: m.MoreTab })))

const TABS: Record<TabId, () => ReactNode> = {
  now: () => <NowPlayingTab />,
  trackpad: () => <TrackpadTab />,
  keys: () => <KeysTab />,
  launch: () => <LaunchTab />,
  more: () => <MoreTab />,
}

function usePrefetchTabs() {
  useEffect(() => {
    const prefetch = () => {
      void Promise.all([loadTrackpad(), loadKeys(), loadLaunch(), loadMore()])
    }
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(prefetch, { timeout: 2000 })
      return () => {
        window.cancelIdleCallback(id)
      }
    }
    const timer = setTimeout(prefetch, 500)
    return () => {
      clearTimeout(timer)
    }
  }, [])
}

function TabFallback() {
  return (
    <div className="flex flex-col gap-4 pt-2">
      <Skeleton label="Loading" className="h-12 w-full" />
      <Skeleton label="Loading" className="h-64 w-full" />
    </div>
  )
}

function useStatusText() {
  const status = useConnection((s) => s.status)
  const session = useConnection((s) => s.session)
  const latency = useConnection((s) => s.latencyMs)
  if (status.kind === 'connected' && session !== null) {
    return {
      ok: true,
      text: `Connected to ${session.hostName}${latency !== null ? ` · ${String(latency)}ms` : ''}`,
    }
  }
  if (status.kind === 'offline') {
    return {
      ok: false,
      text: `Can't reach your laptop. Is it on the same Wi-Fi? Retrying in ${String(Math.ceil(status.retryInMs / 1000))}s.`,
    }
  }
  if (status.kind === 'connecting') return { ok: false, text: "Can't reach your laptop. Is it on the same Wi-Fi?" }
  return { ok: false, text: 'Reconnecting...' }
}

/**
 * One header row for everything above the content: the connection status, or a dot plus
 * the context suggestion when there is one. Keeping it to one row leaves the screen for
 * the controls.
 */
/** Text the laptop sent from its tray or dashboard, with a button to copy it here. */
function IncomingText() {
  const text = useIncoming((s) => s.text)
  const dismiss = useIncoming((s) => s.dismiss)
  return (
    <Sheet open={text !== null} title="From your laptop" onClose={dismiss}>
      {text !== null && (
        <div className="flex flex-col gap-3">
          <p className="max-h-60 overflow-y-auto rounded-xl bg-[var(--color-bg-raised)] px-3 py-2 text-sm break-words whitespace-pre-wrap select-text">
            {text === '' ? 'The laptop clipboard has no text.' : text}
          </p>
          {text !== '' && (
            <Button
              variant="primary"
              size="lg"
              onClick={() => {
                void copyToPhone(text).then((ok) => {
                  useUi.getState().showToast(ok ? 'success' : 'error', ok ? 'Copied to this phone.' : 'Select the text and copy it.')
                  if (ok) dismiss()
                })
              }}
            >
              Copy to this phone
            </Button>
          )}
        </div>
      )}
    </Sheet>
  )
}

function ThemeToggle() {
  const theme = useUi((s) => s.theme)
  const toggle = useUi((s) => s.toggleTheme)
  const dark = theme === 'dark'
  return (
    <IconButton label={dark ? 'Switch to light mode' : 'Switch to dark mode'} variant="plain" onClick={toggle}>
      {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </IconButton>
  )
}

function Header() {
  const status = useStatusText()
  const suggestion = useContextSuggestion()
  const compact = status.ok && suggestion.suggestion !== null
  return (
    <header className="px-4 pt-safe">
      <div className="flex min-h-12 items-center justify-center gap-2 py-1 short:py-0.5 land:py-0.5">
        {compact ? (
          <p role="status" className="flex h-11 w-5 shrink-0 items-center justify-center">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-[var(--color-success)]" />
            <span className="sr-only">{status.text}</span>
          </p>
        ) : (
          <StatusPill tone={status.ok ? 'ok' : 'warn'}>{status.text}</StatusPill>
        )}
        {status.ok && <ContextBanner suggestion={suggestion} />}
        <ThemeToggle />
      </div>
    </header>
  )
}

export function Shell() {
  const tab = useUi((s) => s.tab)
  const direction = useUi((s) => s.direction)
  const setTab = useUi((s) => s.setTab)
  const swipe = useRef<{ x: number; y: number; t: number } | null>(null)
  usePrefetchTabs()
  useLockScreen()

  // Swipe left/right anywhere in the content to change tabs (not on the trackpad,
  // and not when the touch starts on a slider or other [data-no-swipe] control).
  const onPointerDown = (e: React.PointerEvent) => {
    const target = e.target as HTMLElement
    if (tab === 'trackpad' || e.pointerType === 'mouse' || target.closest('[data-no-swipe]') !== null) {
      swipe.current = null
      return
    }
    swipe.current = { x: e.clientX, y: e.clientY, t: e.timeStamp }
  }
  const onPointerUp = (e: React.PointerEvent) => {
    const start = swipe.current
    swipe.current = null
    if (start === null) return
    const dx = e.clientX - start.x
    const dy = e.clientY - start.y
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy) * 2) return
    if (e.timeStamp - start.t > SWIPE_MAX_MS) return
    const next = neighbourTab(tab, dx < 0 ? 1 : -1)
    if (next !== null) setTab(next)
  }

  return (
    <div className="relative isolate flex h-full flex-col land:flex-row">
      <Backdrop visible={tab === 'now'} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Header />
      <main
        className="relative min-h-0 flex-1 overflow-hidden"
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          swipe.current = null
        }}
      >
        <AnimatePresence initial={false} custom={direction} mode="popLayout">
          <motion.div
            key={tab}
            custom={direction}
            variants={{
              enter: (d: number) => ({ x: `${String(d * 18)}%`, opacity: 0 }),
              center: { x: 0, opacity: 1 },
              exit: (d: number) => ({ x: `${String(d * -18)}%`, opacity: 0 }),
            }}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ type: 'spring', stiffness: 420, damping: 40 }}
            className="absolute inset-0 flex touch-pan-y flex-col overflow-y-auto px-4 pb-3 short:pb-2 land:pb-2 md:mx-auto md:w-full md:max-w-2xl"
          >
            <Suspense fallback={<TabFallback />}>{TABS[tab]()}</Suspense>
          </motion.div>
        </AnimatePresence>
      </main>
      </div>
      <TabBar />
      <IncomingText />
    </div>
  )
}
