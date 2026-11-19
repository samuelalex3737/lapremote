const HINTS_KEY = 'lapremote.hintsSeen'

/** Whether the gesture hints were already dismissed in this browser session. */
export function hintsSeen(): boolean {
  try {
    return sessionStorage.getItem(HINTS_KEY) === '1'
  } catch {
    return false
  }
}

export function markHintsSeen(): void {
  try {
    sessionStorage.setItem(HINTS_KEY, '1')
  } catch {
    // Blocked storage: the hints simply show again next visit.
  }
}
