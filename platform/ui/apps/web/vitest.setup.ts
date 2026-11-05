import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

/**
 * jsdom has no `matchMedia`, and `ThemeProvider` subscribes to it while the preference is
 * `system` — which is the default on an unauthenticated screen, so every render of the auth
 * layout needs this. Kept to the minimum the provider actually calls, rather than copying the
 * package's controllable stub: no test here asserts on the resolved palette.
 */
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    media: query,
    matches: false,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })),
});

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.style.removeProperty('color-scheme');
  document.cookie = 'pms-theme=; max-age=0; path=/';
});
