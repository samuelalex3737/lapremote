import { useEffect, useRef } from 'react'
import { currentSession, positionAt } from '../lib/media.ts'
import { LOCK_ACTIONS, lockActionMessage, lockMetadata, silentWavDataUrl } from '../lib/lockscreen.ts'
import { client, mediaStore, useMedia } from '../store/remote.ts'
import { useUi } from '../store/ui.ts'

/**
 * Keeps the phone's lock-screen controls in step with what plays on the laptop.
 * Starts on the first tap after opening (browsers only allow sound from a tap) and only
 * while something is playing or paused on the laptop.
 */
export function useLockScreen(): void {
  const enabled = useUi((s) => s.lockScreen)
  const { media } = useMedia()
  const audio = useRef<HTMLAudioElement | null>(null)
  const unlocked = useRef(false)
  const session = media === null ? null : currentSession(media)
  const sessionId = session?.id ?? null
  const latestId = useRef(sessionId)
  useEffect(() => {
    latestId.current = sessionId
  }, [sessionId])

  // Wait for the first tap: browsers refuse to start sound without one.
  useEffect(() => {
    if (!enabled || !('mediaSession' in navigator)) return
    const unlock = () => {
      unlocked.current = true
      if (audio.current === null) {
        const el = new Audio(silentWavDataUrl())
        el.loop = true
        audio.current = el
      }
      if (latestId.current !== null) void audio.current.play().catch(() => undefined)
    }
    document.addEventListener('pointerdown', unlock, { once: true })
    return () => {
      document.removeEventListener('pointerdown', unlock)
    }
  }, [enabled])

  // Lock-screen buttons send the usual media messages.
  useEffect(() => {
    if (!enabled || !('mediaSession' in navigator)) return
    for (const action of LOCK_ACTIONS) {
      try {
        navigator.mediaSession.setActionHandler(action, (details) => {
          const message = lockActionMessage(action, latestId.current, { seekTime: details.seekTime ?? null })
          if (message !== null) client.send(message.type, message.payload)
        })
      } catch {
        // This browser doesn't support that action.
      }
    }
    return () => {
      for (const action of LOCK_ACTIONS) {
        try {
          navigator.mediaSession.setActionHandler(action, null)
        } catch {
          // Not supported here.
        }
      }
    }
  }, [enabled])

  // What's playing, shown on the lock screen.
  useEffect(() => {
    // Some browsers have mediaSession but no MediaMetadata: no lock-screen info there.
    if (!('mediaSession' in navigator) || typeof MediaMetadata === 'undefined') return
    const el = audio.current
    if (!enabled || session === null) {
      navigator.mediaSession.metadata = null
      navigator.mediaSession.playbackState = 'none'
      el?.pause()
      return
    }
    navigator.mediaSession.metadata = new MediaMetadata(lockMetadata(session, mediaStore.artwork.get(session.artworkId)))
    navigator.mediaSession.playbackState = session.status === 'playing' ? 'playing' : 'paused'
    const position = positionAt(session, Date.now())
    if (session.duration !== null && session.duration > 0 && position !== null) {
      try {
        navigator.mediaSession.setPositionState({
          duration: session.duration,
          position: Math.min(Math.max(position, 0), session.duration),
          playbackRate: session.status === 'playing' ? session.rate || 1 : 1,
        })
      } catch {
        // Older browsers: no position on the lock screen.
      }
    }
    if (unlocked.current && el?.paused === true) void el.play().catch(() => undefined)
  }, [enabled, session])

  useEffect(
    () => () => {
      audio.current?.pause()
      audio.current = null
    },
    [],
  )
}
