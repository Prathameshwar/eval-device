/*
 * Theme resolution and persistence — pure logic, no React.
 *
 * The preference is one of four values; the applied palette is one of three. `resolveTheme` is the *only* place that mapping lives, so
 * the pre-paint script, the provider and the tests cannot disagree about what a user's
 * stored `system` means on a given machine.
 *
 * Nothing here touches the DOM at module scope: these modules are imported by a server
 * component tree before a `document` exists.
 */

export const THEME_PREFERENCES = ['light', 'dark', 'ledger', 'system'] as const;

export type ThemePreference = (typeof THEME_PREFERENCES)[number];

/** The three real palettes — `system` never reaches the DOM, only what it resolves to. */
export type ResolvedTheme = 'light' | 'dark' | 'ledger';

/** One name for both stores: the cookie makes server-rendered HTML correct on first paint,
 * localStorage survives a cookie clear. */
export const THEME_COOKIE = 'pms-theme';
export const THEME_STORAGE_KEY = 'pms-theme';

/** One year — long enough that a returning user never sees the wrong first paint. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

const PREFERS_DARK = '(prefers-color-scheme: dark)';

export function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === 'string' && (THEME_PREFERENCES as readonly string[]).includes(value);
}

/**
 * The single resolution rule. `prefersDark` is passed in rather than read from
 * `matchMedia` so this stays pure and testable, and so the caller owns the subscription.
 */
export function resolveTheme(preference: ThemePreference, prefersDark: boolean): ResolvedTheme {
  if (preference === 'system') return prefersDark ? 'dark' : 'light';
  return preference;
}

/** `ledger` is warm paper, not a dark palette — native controls must stay light on it. */
export function colorSchemeFor(resolved: ResolvedTheme): 'dark' | 'light' {
  return resolved === 'dark' ? 'dark' : 'light';
}

function readCookiePreference(): ThemePreference | null {
  if (typeof document === 'undefined') return null;
  const match = new RegExp(`(?:^|;\\s*)${THEME_COOKIE}=([^;]*)`).exec(document.cookie);
  if (!match?.[1]) return null;
  // A hand-edited or truncated cookie must not blow up the read path.
  let value: string;
  try {
    value = decodeURIComponent(match[1]);
  } catch {
    return null;
  }
  return isThemePreference(value) ? value : null;
}

function readLocalPreference(): ThemePreference | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(value) ? value : null;
  } catch {
    // Privacy mode throws on *access*, not just on write.
    return null;
  }
}

/**
 * Cookie before localStorage, per the §2.2 precedence with the session preference removed —
 * that one outranks both and is supplied by the app as `ThemeProvider`'s `initial`.
 * Unknown or corrupt values are ignored rather than repaired.
 */
export function readStoredPreference(): ThemePreference | null {
  return readCookiePreference() ?? readLocalPreference();
}

/** Writes both stores. A failure in either is not worth breaking a theme switch over. */
export function persistPreference(preference: ThemePreference): void {
  try {
    document.cookie = `${THEME_COOKIE}=${preference}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`;
  } catch {
    /* no document, or cookies blocked */
  }
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* quota exceeded, or privacy mode */
  }
}

/** `color-scheme` rides along so scrollbars, form controls and browser chrome follow. */
export function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', resolved);
  root.style.setProperty('color-scheme', colorSchemeFor(resolved));
}

/**
 * The pre-paint snippet, injected synchronously by each app's root layout.
 *
 * It runs before any bundle, so it cannot reference the functions above and must
 * re-implement read → resolve → apply inline; the literals are interpolated from the
 * constants so the two copies can't drift on a rename. The whole body is wrapped in
 * try/catch: a storage exception here would leave the page unpainted, and no theme is
 * worse than a blank screen.
 */
export const themeScript = `(function(){try{
var v=${JSON.stringify(THEME_PREFERENCES)};
var p=null;
var m=document.cookie.match(/(?:^|;\\s*)${THEME_COOKIE}=([^;]*)/);
if(m){try{var c=decodeURIComponent(m[1]);if(v.indexOf(c)>-1)p=c;}catch(e){}}
if(!p){try{var s=localStorage.getItem('${THEME_STORAGE_KEY}');if(v.indexOf(s)>-1)p=s;}catch(e){}}
if(!p)p='system';
var r=p==='system'?(window.matchMedia('${PREFERS_DARK}').matches?'dark':'light'):p;
var d=document.documentElement;
d.setAttribute('data-theme',r);
d.style.setProperty('color-scheme',r==='dark'?'dark':'light');
}catch(e){}})();`;

/** The media query the provider subscribes to while the preference is `system`. */
export const PREFERS_DARK_QUERY = PREFERS_DARK;
