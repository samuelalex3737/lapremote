export interface DeviceIdentity {
  name: string
  platform: 'ios' | 'android' | 'other'
}

/** A friendly default name and platform for this phone, used when pairing. */
export function detectDevice(userAgent: string, maxTouchPoints = 0): DeviceIdentity {
  if (userAgent.includes('iPad') || (userAgent.includes('Macintosh') && maxTouchPoints > 1)) {
    return { name: 'iPad', platform: 'ios' }
  }
  if (/iPhone|iPod/.test(userAgent)) return { name: 'iPhone', platform: 'ios' }
  if (userAgent.includes('Android')) {
    const model = /Android [\d.]+; ([^;)]+?)(?: Build|\))/.exec(userAgent)?.[1]?.trim()
    const name = model && model !== 'K' ? model : 'Android phone'
    return { name: name.slice(0, 64), platform: 'android' }
  }
  return { name: 'Browser', platform: 'other' }
}

export function socketUrl(location: Pick<Location, 'protocol' | 'host'>): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws`
}
