'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  PREFERS_DARK_QUERY,
  applyTheme,
  persistPreference,
  readStoredPreference,
  resolveTheme,
  type ResolvedTheme,
  type ThemePreference,
} from '../lib/theme';

type ThemeContextValue = {
  /** What the user chose — one of four values, including `system`. */
  preference: ThemePreference;
  /** What is painted — one of three palettes. Never stored. */
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

type ThemeProviderProps = {
  /**
   * The session's `user.theme`, which outranks both client stores (§2.2). Omitted for an
   * unauthenticated app, which then falls back to the cookie / localStorage the pre-paint
   * script already read — so provider and first paint agree and nothing flashes.
   */
  initial?: ThemePreference;
  /** Called on every change; the app uses it to PATCH the user record. */
  onChange?: (preference: ThemePreference) => void;
  children: ReactNode;
};

export function ThemeProvider({ initial, onChange, children }: ThemeProviderProps) {
  const [preference, setPreferenceState] = useState<ThemePreference>(
    // The server and first client render must agree. The pre-paint script already
    // applies the saved palette; adopt browser preferences after hydration.
    initial ?? 'system',
  );
  const [prefersDark, setPrefersDark] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setPreferenceState(initial ?? readStoredPreference() ?? 'system');
    setPrefersDark(window.matchMedia(PREFERS_DARK_QUERY).matches);
    setReady(true);
  }, [initial]);

  // Only while `system` is chosen. A live subscription under an explicit `light` would keep
  // firing re-renders for a value that can't affect the palette.
  useEffect(() => {
    if (!ready || preference !== 'system') return;
    const query = window.matchMedia(PREFERS_DARK_QUERY);
    setPrefersDark(query.matches);
    const onMediaChange = (event: MediaQueryListEvent): void => setPrefersDark(event.matches);
    query.addEventListener('change', onMediaChange);
    return () => query.removeEventListener('change', onMediaChange);
  }, [preference, ready]);

  const resolved = resolveTheme(preference, prefersDark);

  useEffect(() => {
    if (ready) applyTheme(resolved);
  }, [resolved, ready]);

  const setPreference = useCallback(
    (next: ThemePreference) => {
      setPreferenceState(next);
      persistPreference(next);
      // Paint immediately rather than waiting for the effect, so a click is never a frame late.
      applyTheme(resolveTheme(next, window.matchMedia(PREFERS_DARK_QUERY).matches));
      onChange?.(next);
    },
    [onChange],
  );

  const value = useMemo<ThemeContextValue>(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error(
      'useTheme must be used inside a <ThemeProvider>. Wrap the app root (or the nearest client boundary) in <ThemeProvider> from @pms/ui.',
    );
  }
  return value;
}
