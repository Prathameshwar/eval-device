import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

/**
 * The app's own tests, in the same shape as `@pms/ui`'s: jsdom, globals, `css: false`.
 *
 * `css: false` is why `tests/auth-css.test.ts` exists — component tests here cannot see a
 * misspelt class name either, so the stylesheet is checked as text instead, exactly as the
 * package checks its own.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      'server-only': fileURLToPath(new URL('./tests/server-only.ts', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
