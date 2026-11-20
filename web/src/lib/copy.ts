/**
 * Put text on the phone's clipboard. The Clipboard API only exists on secure pages, so on
 * plain http this falls back to a hidden text box and the older copy command, which works
 * from a tap.
 */
export async function copyToPhone(text: string): Promise<boolean> {
  if (window.isSecureContext && 'clipboard' in navigator) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Permission refused: try the fallback.
    }
  }
  const box = document.createElement('textarea')
  box.value = text
  box.setAttribute('readonly', '')
  box.style.position = 'fixed'
  box.style.opacity = '0'
  box.style.pointerEvents = 'none'
  document.body.append(box)
  box.select()
  box.setSelectionRange(0, text.length)
  try {
    // Deprecated, but the only way to copy on a plain-http page.
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    box.remove()
  }
}

/** A link worth opening in the laptop's browser: http(s) with a host, nothing else. */
export function asLink(text: string): string | null {
  const value = text.trim()
  if (value === '' || /\s/.test(value)) return null
  const withScheme = /^https?:\/\//i.test(value) ? value : /^[\w-]+(\.[\w-]+)+(\/|$)/.test(value) ? `https://${value}` : null
  if (withScheme === null) return null
  try {
    const url = new URL(withScheme)
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname.includes('.') ? url.toString() : null
  } catch {
    return null
  }
}
