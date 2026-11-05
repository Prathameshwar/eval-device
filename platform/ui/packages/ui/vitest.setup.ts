import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

/**
 * jsdom has no `matchMedia`. The theme system depends on it for `system` resolution, so
 * provide a controllable stub: tests set `__setPrefersDark(true)` and, if they need to
 * simulate the OS flipping, call the registered listeners via `__emitPrefersDark(...)`.
 */
type Listener = (event: MediaQueryListEvent) => void;

let prefersDark = false;
const listeners = new Set<Listener>();

function setPrefersDark(value: boolean): void {
  prefersDark = value;
}

/** Flip the OS preference and notify every subscriber, as a real browser would. */
function emitPrefersDark(value: boolean): void {
  prefersDark = value;
  for (const listener of listeners) {
    listener({ matches: value } as MediaQueryListEvent);
  }
}

Object.defineProperty(globalThis, '__setPrefersDark', { value: setPrefersDark, writable: true });
Object.defineProperty(globalThis, '__emitPrefersDark', { value: emitPrefersDark, writable: true });

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    media: query,
    get matches() {
      return query.includes('dark') ? prefersDark : false;
    },
    onchange: null,
    addEventListener: (_: string, listener: Listener) => {
      listeners.add(listener);
    },
    removeEventListener: (_: string, listener: Listener) => {
      listeners.delete(listener);
    },
    addListener: (listener: Listener) => {
      listeners.add(listener);
    },
    removeListener: (listener: Listener) => {
      listeners.delete(listener);
    },
    dispatchEvent: () => false,
  })),
});

beforeEach(() => {
  prefersDark = false;
  listeners.clear();
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.style.removeProperty('color-scheme');
  document.cookie = 'pms-theme=; max-age=0; path=/';
});
