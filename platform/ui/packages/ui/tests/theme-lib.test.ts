/**
 * Theme resolution, persistence, and the pre-paint script.
 *
 * The script is tested by *evaluating the exported string* in the jsdom document rather
 * than by reading it: the no-flash guarantee is that the snippet and the provider agree on
 * the same inputs, and only running it proves that.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  THEME_COOKIE,
  THEME_PREFERENCES,
  THEME_STORAGE_KEY,
  applyTheme,
  colorSchemeFor,
  isThemePreference,
  persistPreference,
  readStoredPreference,
  resolveTheme,
  themeScript,
  type ThemePreference,
} from '../src/lib/theme';

declare function __setPrefersDark(value: boolean): void;

function setCookie(value: string): void {
  document.cookie = `${THEME_COOKIE}=${value}; path=/`;
}

function runThemeScript(): void {
  new Function(themeScript)();
}

describe('THEME_PREFERENCES', () => {
  it('is the four-value catalogue identity validates against', () => {
    expect(THEME_PREFERENCES).toEqual(['light', 'dark', 'ledger', 'system']);
  });
});

describe('resolveTheme', () => {
  const cases: ReadonlyArray<[ThemePreference, boolean, string]> = [
    ['light', false, 'light'],
    ['light', true, 'light'],
    ['dark', false, 'dark'],
    ['dark', true, 'dark'],
    ['ledger', false, 'ledger'],
    ['ledger', true, 'ledger'],
    ['system', false, 'light'],
    ['system', true, 'dark'],
  ];

  it.each(cases)('%s with prefersDark=%s resolves to %s', (preference, prefersDark, expected) => {
    expect(resolveTheme(preference, prefersDark)).toBe(expected);
  });
});

describe('colorSchemeFor', () => {
  it('reports dark only for the dark palette — ledger is warm paper, not a dark scheme', () => {
    expect(colorSchemeFor('dark')).toBe('dark');
    expect(colorSchemeFor('light')).toBe('light');
    expect(colorSchemeFor('ledger')).toBe('light');
  });
});

describe('isThemePreference', () => {
  it.each(THEME_PREFERENCES)('accepts %s', (value) => {
    expect(isThemePreference(value)).toBe(true);
  });

  it('rejects anything outside the catalogue, including near-misses and non-strings', () => {
    const junk: unknown[] = ['sepia', '', 'LIGHT', ' dark', null, undefined, 42, ['dark'], {}];
    expect(junk.filter(isThemePreference)).toEqual([]);
  });
});

describe('readStoredPreference', () => {
  it('returns null when nothing is stored, so the caller can fall back to system', () => {
    expect(readStoredPreference()).toBeNull();
  });

  it('prefers the cookie over localStorage — the cookie is what the server rendered from', () => {
    setCookie('ledger');
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(readStoredPreference()).toBe('ledger');
  });

  it('falls through to localStorage when no cookie survives', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(readStoredPreference()).toBe('dark');
  });

  it('ignores a corrupt cookie and a corrupt stored value rather than repairing them', () => {
    setCookie('sepia');
    localStorage.setItem(THEME_STORAGE_KEY, '{"theme":"dark"}');
    expect(readStoredPreference()).toBeNull();
  });

  it('ignores a percent-mangled cookie value', () => {
    setCookie('%E0%A4');
    expect(readStoredPreference()).toBeNull();
  });

  it('does not propagate a localStorage that throws on access (privacy mode)', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: access denied');
    });
    try {
      expect(readStoredPreference()).toBeNull();
    } finally {
      getItem.mockRestore();
    }
  });
});

describe('persistPreference', () => {
  it.each(THEME_PREFERENCES)('round-trips %s through readStoredPreference', (preference) => {
    persistPreference(preference);
    expect(readStoredPreference()).toBe(preference);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe(preference);
    expect(document.cookie).toContain(`${THEME_COOKIE}=${preference}`);
  });

  it('does not throw when localStorage rejects the write', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    try {
      expect(() => persistPreference('dark')).not.toThrow();
      // The cookie still landed, so the next first paint is still correct.
      expect(readStoredPreference()).toBe('dark');
    } finally {
      setItem.mockRestore();
    }
  });
});

describe('applyTheme', () => {
  it.each([
    ['light', 'light'],
    ['dark', 'dark'],
    ['ledger', 'light'],
  ] as const)('sets data-theme=%s with color-scheme %s', (resolved, scheme) => {
    applyTheme(resolved);
    expect(document.documentElement.getAttribute('data-theme')).toBe(resolved);
    expect(document.documentElement.style.getPropertyValue('color-scheme')).toBe(scheme);
  });
});

describe('themeScript', () => {
  it('paints light when nothing is stored and the OS is light', () => {
    __setPrefersDark(false);
    runThemeScript();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(document.documentElement.style.getPropertyValue('color-scheme')).toBe('light');
  });

  it('resolves an unstored preference through the OS, as system would', () => {
    __setPrefersDark(true);
    runThemeScript();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.style.getPropertyValue('color-scheme')).toBe('dark');
  });

  it('resolves a stored system preference live against a dark OS', () => {
    setCookie('system');
    __setPrefersDark(true);
    runThemeScript();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it.each(THEME_PREFERENCES)(
    'paints exactly what the provider would for a stored %s (cookie)',
    (preference) => {
      __setPrefersDark(true);
      setCookie(preference);
      runThemeScript();
      expect(document.documentElement.getAttribute('data-theme')).toBe(
        resolveTheme(preference, true),
      );
      expect(document.documentElement.style.getPropertyValue('color-scheme')).toBe(
        colorSchemeFor(resolveTheme(preference, true)),
      );
    },
  );

  it.each(THEME_PREFERENCES)(
    'paints exactly what the provider would for a stored %s (localStorage)',
    (preference) => {
      __setPrefersDark(false);
      localStorage.setItem(THEME_STORAGE_KEY, preference);
      runThemeScript();
      expect(document.documentElement.getAttribute('data-theme')).toBe(
        resolveTheme(preference, false),
      );
    },
  );

  it('prefers the cookie over localStorage, exactly as readStoredPreference does', () => {
    setCookie('ledger');
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    runThemeScript();
    expect(document.documentElement.getAttribute('data-theme')).toBe('ledger');
  });

  it('ignores a corrupt cookie and falls back to the OS', () => {
    setCookie('sepia');
    __setPrefersDark(true);
    runThemeScript();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('still paints when localStorage throws — a blank page is worse than any theme', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: access denied');
    });
    try {
      __setPrefersDark(true);
      expect(() => runThemeScript()).not.toThrow();
      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    } finally {
      getItem.mockRestore();
    }
  });

  it('swallows a failure it cannot recover from rather than throwing at the top of the page', () => {
    const matchMedia = vi.spyOn(window, 'matchMedia').mockImplementation(() => {
      throw new Error('no matchMedia');
    });
    try {
      expect(() => runThemeScript()).not.toThrow();
      expect(document.documentElement.getAttribute('data-theme')).toBeNull();
    } finally {
      matchMedia.mockRestore();
    }
  });
});
