/**
 * @file Frontend build and development-server configuration.
 * Combines Tailwind, React, and React Compiler transforms. In development, the
 * /api proxy strips its prefix before forwarding to the local orchestrator API;
 * production routing is configured outside this development-only proxy.
 */
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    babel({ presets: [reactCompilerPreset()] })
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        /**
         * Maps frontend-relative API URLs to backend endpoint paths.
         * @param {string} path - Incoming proxied request path.
         * @returns {string} Backend path without the /api prefix.
         */
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
