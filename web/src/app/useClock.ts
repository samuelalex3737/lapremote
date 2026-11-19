import { useEffect, useState } from 'react'

/** Wall-clock milliseconds, refreshed every `every` ms while `active`. */
export function useClock(active: boolean, every = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => {
      setNow(Date.now())
    }, every)
    return () => {
      clearInterval(t)
    }
  }, [active, every])
  return now
}
