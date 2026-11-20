import { useEffect } from 'react'
import { suggestMode } from '../lib/adaptive.ts'
import { useLaptopContext } from '../store/remote.ts'
import { useUi } from '../store/ui.ts'

/**
 * What is in focus on the laptop suggests a better control surface ("Netflix in focus -
 * movie controls"). With auto-switch on, the switch happens by itself (never away from the
 * trackpad mid-use) and no suggestion is shown.
 */
export function useContextSuggestion() {
  const context = useLaptopContext((s) => s.context)
  const { tab, mode, dismissedBanner, autoSwitch, setMode, setTab, dismissBanner } = useUi()
  const suggestion = suggestMode(context)
  const effective = mode === 'auto' ? 'music' : mode
  const alreadyThere = suggestion !== null && suggestion.mode === effective && tab === 'now'

  useEffect(() => {
    if (!autoSwitch || suggestion === null) return
    setMode(suggestion.mode)
    if (tab !== 'trackpad') setTab('now')
    // Only react to the context changing, not to tab changes the person makes afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSwitch, suggestion?.key])

  const show = suggestion !== null && !alreadyThere && dismissedBanner !== suggestion.key && !autoSwitch
  return {
    suggestion: show ? suggestion : null,
    accept: () => {
      if (suggestion === null) return
      setMode(suggestion.mode)
      setTab('now')
    },
    dismiss: () => {
      if (suggestion !== null) dismissBanner(suggestion.key)
    },
  }
}

export type ContextSuggestion = ReturnType<typeof useContextSuggestion>
