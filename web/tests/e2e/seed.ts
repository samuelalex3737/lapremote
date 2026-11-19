/**
 * Seeds an isolated LAPREMOTE_HOME with one paired device so e2e tests can
 * resume a session without knowing the live pairing code.
 */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export const E2E_DEVICE_ID = 'e2e0000000000001'
export const E2E_TOKEN = 'e2e-only-token-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
export const E2E_DEVICE_NAME = 'E2E phone'

/** One temp home per Playwright run, shared with workers through the environment. */
export function e2eHome(): string {
  const existing = process.env.LAPREMOTE_E2E_HOME
  if (existing !== undefined && existing !== '') return existing
  const home = mkdtempSync(join(tmpdir(), 'lapremote-e2e-'))
  process.env.LAPREMOTE_E2E_HOME = home
  return home
}

export function seedHome(home: string): void {
  const path = join(home, 'devices.json')
  if (existsSync(path)) return
  mkdirSync(home, { recursive: true })
  const devices = {
    version: 1,
    devices: [
      {
        device_id: E2E_DEVICE_ID,
        name: E2E_DEVICE_NAME,
        platform: 'ios',
        role: 'owner',
        token_hash: createHash('sha256').update(E2E_TOKEN).digest('hex'),
        paired_at: Date.now() / 1000,
        last_seen_at: null,
      },
    ],
  }
  writeFileSync(path, JSON.stringify(devices, null, 2))
}
