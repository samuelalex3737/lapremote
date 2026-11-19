/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// The agent port the dev proxy forwards to. Playwright runs its own agent on a
// separate port so it never collides with a real agent on 7777.
const agentPort = Number(process.env.LAPREMOTE_AGENT_PORT ?? '7777')
const agentHttp = `http://127.0.0.1:${String(agentPort)}`
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
  version: string
}

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      // Service workers need a secure context (HTTPS or localhost). On plain LAN http
      // the browser skips registration and the app works the same, just not offline.
      manifest: {
        name: 'LapRemote',
        short_name: 'LapRemote',
        description: 'Control your laptop from your phone.',
        theme_color: '#07070b',
        background_color: '#07070b',
        display: 'standalone',
        orientation: 'any',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,woff2}', 'icons/*.png'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/ws/, /^\/desktop/, /^\/calibration/],
      },
    }),
  ],
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
