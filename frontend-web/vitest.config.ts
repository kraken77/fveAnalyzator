import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Testový config: jsdom pro component testy (oddělený od vite.config.ts,
// aby `vite build` nebyl zasažen testovými nastaveními).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    // @testing-library/react vyžaduje globální afterEach pro automatický cleanup
    // mezi testy (bez toho se renderů hromadí).
    globals: true,
  },
})
