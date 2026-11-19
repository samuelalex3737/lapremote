import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

// Ports used only by the e2e run, so a real agent on 7777 is never touched.
const AGENT_PORT = 7787
const WEB_PORT = 5183

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${String(WEB_PORT)}`,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'iphone-15', use: { ...devices['iPhone 15'] } },
    { name: 'pixel-8', use: { ...devices['Pixel 8'] } },
  ],
  webServer: [
    {
      command: `uv run --project ../agent python -m lapremote --port ${String(AGENT_PORT)}`,
      url: `http://127.0.0.1:${String(AGENT_PORT)}/api/health`,
      env: { LAPREMOTE_HOME: join(tmpdir(), 'lapremote-e2e-home') },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --port ${String(WEB_PORT)} --strictPort`,
      url: `http://127.0.0.1:${String(WEB_PORT)}`,
      env: { LAPREMOTE_AGENT_PORT: String(AGENT_PORT) },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
