import { z } from 'zod'

export const credentialsSchema = z.object({
  deviceId: z.string().min(1),
  token: z.string().min(1),
})
export type Credentials = z.infer<typeof credentialsSchema>

export interface CredentialStore {
  load(): Credentials | null
  save(credentials: Credentials): void
  clear(): void
}

export const CREDENTIALS_KEY = 'lapremote.credentials.v1'

function browserStorage(): Storage | null {
  try {
    return globalThis.localStorage
  } catch {
    // Some browsers throw on access when site data is blocked.
    return null
  }
}

/** localStorage-backed store. Storage can be blocked (private mode), so every call is guarded. */
export function localCredentialStore(storage: Storage | null = browserStorage()): CredentialStore {
  return {
    load() {
      try {
        const raw = storage?.getItem(CREDENTIALS_KEY)
        if (raw == null) return null
        const parsed = credentialsSchema.safeParse(JSON.parse(raw))
        return parsed.success ? parsed.data : null
      } catch {
        return null
      }
    },
    save(credentials) {
      try {
        storage?.setItem(CREDENTIALS_KEY, JSON.stringify(credentials))
      } catch {
        // Storage blocked: the phone stays paired for this session only.
      }
    },
    clear() {
      try {
        storage?.removeItem(CREDENTIALS_KEY)
      } catch {
        // Nothing stored, nothing to clear.
      }
    },
  }
}

export function memoryCredentialStore(initial: Credentials | null = null): CredentialStore {
  let value = initial
  return {
    load: () => value,
    save: (c) => {
      value = c
    },
    clear: () => {
      value = null
    },
  }
}
