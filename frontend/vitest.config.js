import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate from vite.config.js on purpose: the Tailwind v4 plugin is part of the
// build pipeline and not needed (and slows down) unit tests, so the test runner
// uses a minimal plugin set.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
