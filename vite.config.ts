import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'AnaesthesiaVN – Hỗ trợ Lâm sàng Gây mê',
        short_name: 'AnaesthesiaVN',
        description: 'Công cụ Hỗ trợ Quyết định Lâm sàng Gây mê cho bác sĩ Việt Nam',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        // Cache-first: drug DB, calculation bundles
        runtimeCaching: [
          {
            urlPattern: /\/api\/drugs/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'drug-database',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: /\/api\/history/,
            handler: 'NetworkFirst',
            options: { cacheName: 'history-cache' },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { '@': '/src' },
  },
})
