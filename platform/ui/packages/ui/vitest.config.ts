import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

/**
 * @pms/ui tests its own primitives, rather than leaning on a consuming app to do it.
 * Tests import from source module paths (`../src/components/Card`) so a package with a
 * half-written barrel file still tests cleanly.
 *
 * The theme system tests (`tests/themes.test.ts`) read the stylesheets as text, so they
 * need no CSS pipeline; components style via class names, hence `css: false`.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    include: ['tests/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts', 'src/**/*.tsx'],
      exclude: ['src/index.ts', '**/*.d.ts'],
      thresholds: { lines: 90, functions: 90, statements: 90, branches: 85 },
    },
  },
});
