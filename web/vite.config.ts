/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The agent port the dev proxy forwards to. Playwright runs its own agent on a
// separate port so it never collides with a real agent on 7777.
const agentPort = Number(process.env.LAPREMOTE_AGENT_PORT ?? '7777')
const agentHttp = `http://127.0.0.1:${String(agentPort)}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: agentHttp, changeOrigin: false },
      '/ws': { target: agentHttp, ws: true, changeOrigin: false },
    },
  },
  build: {
    // The agent serves the built app from its package (git-ignored).
    outDir: fileURLToPath(new URL('../agent/lapremote/static', import.meta.url)),
    emptyOutDir: true,
  },
  test: {
    include: ['tests/unit/**/*.test.ts'],
    environment: 'node',
  },
})
