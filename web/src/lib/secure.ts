/** True when the browser grants powerful features (mic, motion) to this page. */
export function isSecure(): boolean {
  return typeof window !== 'undefined' && window.isSecureContext
}
