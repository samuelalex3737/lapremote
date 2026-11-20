import { useEffect } from 'react'
import { suggestMode } from '../lib/adaptive.ts'
import { CALL_LAYOUTS, matchLayout } from '../lib/layouts.ts'
import { useLaptopContext, useLayouts } from '../store/remote.ts'
import { useUi } from '../store/ui.ts'

/**
 * What is in focus on the laptop suggests a better control surface ("Netflix in focus -
 * movie controls"). With auto-switch on, the switch happens by itself (never away from the
 * trackpad mid-use) and no suggestion is shown.
 */
export function useContextSuggestion() {
  const context = useLaptopContext((s) => s.context)
  const layouts = useLayouts((s) => s.layouts)
  const { tab, mode, dismissedBanner, autoSwitch, keysMode, setMode, setTab, setKeysMode, setLayoutPick, dismissBanner } =
    useUi()
  const suggestion = suggestMode(context)
  const effective = mode === 'auto' ? 'music' : mode
  const alreadyThere = suggestion !== null && suggestion.mode === effective && tab === 'now'

  // A call app in front (Zoom, Teams, Meet) offers its call buttons instead.
  const layout = suggestion === null ? matchLayout(layouts, context) : null
  const callLayout = layout !== null && CALL_LAYOUTS.has(layout.id) ? layout : null
  const layoutKey = callLayout !== null && context !== null ? `layout:${callLayout.id}|${context.processName}` : null
  const onCallButtons = tab === 'keys' && keysMode === 'buttons'

  useEffect(() => {
    if (!autoSwitch || suggestion === null) return
    setMode(suggestion.mode)
    if (tab !== 'trackpad') setTab('now')
    // Only react to the context changing, not to tab changes the person makes afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSwitch, suggestion?.key])

  if (callLayout !== null && layoutKey !== null) {
    const showCall = !onCallButtons && dismissedBanner !== layoutKey
    return {
      suggestion: showCall ? { key: layoutKey, text: `${callLayout.name} in focus - call buttons` } : null,
      accept: () => {
        setLayoutPick(null)
        setKeysMode('buttons')
        setTab('keys')
      },
      dismiss: () => {
        dismissBanner(layoutKey)
      },
    }
  }

  const show = suggestion !== null && !alreadyThere && dismissedBanner !== suggestion.key && !autoSwitch
  return {
    suggestion: show ? { key: suggestion.key, text: suggestion.text } : null,
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
