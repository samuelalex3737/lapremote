import { haptic } from '../../lib/haptics.ts'
import type { Shortcut } from '../../lib/protocol.ts'
import { RequestError } from '../../lib/ws.ts'
import { client } from '../../store/remote.ts'
import { useUi } from '../../store/ui.ts'

/** Open a shortcut on the laptop, with a toast for the result. */
export function launch(shortcut: Shortcut): void {
  haptic('click')
  client.request('launch.open', { shortcutId: shortcut.id }).then(
    () => {
      useUi.getState().showToast('success', `Opening ${shortcut.name}`)
    },
    (e: unknown) => {
      useUi.getState().showToast('error', e instanceof RequestError ? e.message : 'That did not work.')
    },
  )
}
