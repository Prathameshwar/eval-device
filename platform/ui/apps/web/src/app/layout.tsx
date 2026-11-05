import type { Metadata, Viewport } from 'next';
import { ThemeProvider, themeScript } from '@pms/ui';
import { publicSite } from '@/lib/public-site';
import '@pms/ui/styles.css';
import '@/styles/brand.css';
import '@/styles/auth.css';
import '@/styles/console.css';
import '@/styles/models.css';

/**
 * The root layout.
 *
 * Three things happen here and nowhere else:
 *
 * 1. `@pms/ui/styles.css` is imported exactly once, as its README requires — the entry pulls
 *    tokens, all three palettes and the component styles in the right order.
 * 2. `themeScript` runs **before** the first paint, so a returning user's dark theme is already
 *    on `<html>` when the HTML arrives instead of flashing light for a frame. It is injected raw
 *    because a bundled module would run too late by definition.
 * 3. `ThemeProvider` takes no `initial`: theme preferences currently stay in the browser. The server
 *    and first client render use `system`; after hydration the provider adopts the stores
 *    already used by the pre-paint script, without overwriting its palette in between.
 *
 * `suppressHydrationWarning` is on `<html>` for one reason: the script above sets `data-theme`
 * and `color-scheme` on that element before React hydrates, so the server's markup legitimately
 * differs from the DOM. It is scoped to the element that the script touches.
 */

const site = publicSite();

export const metadata: Metadata = {
  ...(site.siteUrl ? { metadataBase: new URL(site.siteUrl) } : {}),
  title: {
    default: 'AI Evaluator',
    template: '%s · AI Evaluator',
  },
  description:
    'AI Evaluator scores clinical training conversations with traceable, repeatable evidence.',
  applicationName: 'AI Evaluator',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  /* `--pms-paper` from `theme-light.css` and `theme-dark.css`, so mobile browser chrome matches
   * the page instead of bracketing it in white. Literal because a meta tag cannot read a custom
   * property; if those tokens change, this changes with them. */
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f7f8fb' },
    { media: '(prefers-color-scheme: dark)', color: '#0e1117' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="pms-root">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
