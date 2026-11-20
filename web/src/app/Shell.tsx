import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense, useEffect, useRef, type ReactNode } from 'react'
import { Backdrop } from '../features/nowplaying/Backdrop.tsx'
import { NowPlayingTab } from '../features/nowplaying/NowPlayingTab.tsx'
import { useConnection } from '../store/remote.ts'
import { neighbourTab, useUi, type TabId } from '../store/ui.ts'
import { Skeleton, StatusPill } from '../ui/primitives.tsx'
import { ContextBanner } from './ContextBanner.tsx'
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

function ConnectionPill() {
  const status = useConnection((s) => s.status)
  const session = useConnection((s) => s.session)
  const latency = useConnection((s) => s.latencyMs)
  if (status.kind === 'connected' && session !== null) {
    return (
      <StatusPill tone="ok">
        Connected to {session.hostName}
        {latency !== null && ` · ${String(latency)}ms`}
      </StatusPill>
    )
  }
  return <StatusPill tone="warn">Reconnecting...</StatusPill>
}

function OfflineBanner() {
  const status = useConnection((s) => s.status)
  if (status.kind !== 'offline' && status.kind !== 'connecting') return null
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      className="overflow-hidden"
    >
      <p role="alert" className="mx-4 rounded-2xl bg-[var(--color-warn)]/12 px-4 py-2 text-sm text-[var(--color-warn)] ring-1 ring-inset ring-[var(--color-warn)]/30">
        Can't reach your laptop. Is it on the same Wi-Fi?
        {status.kind === 'offline' && ` Retrying in ${String(Math.ceil(status.retryInMs / 1000))}s.`}
      </p>
    </motion.div>
  )
}

export function Shell() {
  const tab = useUi((s) => s.tab)
  const direction = useUi((s) => s.direction)
  const setTab = useUi((s) => s.setTab)
  const swipe = useRef<{ x: number; y: number; t: number } | null>(null)
  usePrefetchTabs()

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
    <div className="relative isolate flex h-full flex-col">
      <Backdrop visible={tab === 'now'} />
      <header className="flex items-center justify-center px-4 pt-safe">
        <div className="pt-3 pb-2">
          <ConnectionPill />
        </div>
      </header>
      <AnimatePresence>
        <OfflineBanner />
      </AnimatePresence>
      <ContextBanner />
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
            className="absolute inset-0 flex touch-pan-y flex-col overflow-y-auto px-4 pb-4"
          >
            <Suspense fallback={<TabFallback />}>{TABS[tab]()}</Suspense>
          </motion.div>
        </AnimatePresence>
      </main>
      <TabBar />
    </div>
  )
}
