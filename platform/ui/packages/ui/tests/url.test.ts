import { describe, expect, it } from 'vitest';
import { isSafeHref } from '../src/lib/url';

/**
 * The scheme allowlist behind every link the UI renders from a payload (`lib/url`).
 *
 * This is the one check in the design system that is load-bearing for security rather than for
 * presentation: a `javascript:` URL in a supplier's website field executes on click, in the reader's
 * session, with their authority.
 */

/** A control character, built rather than typed: a literal NUL in a source file breaks diffs. */
const ctrl = (code: number) => String.fromCharCode(code);

describe('isSafeHref', () => {
  it('allows what a business application actually links to', () => {
    for (const href of [
      '/customers/cus-008',
      '/customers/cus-008?tab=invoices#totals',
      '#totals',
      'https://example.test/portal',
      'http://example.test/portal',
      'HTTPS://EXAMPLE.TEST',
      'mailto:ada@example.test',
      'tel:+919876543210',
    ]) {
      expect(isSafeHref(href), href).toBe(true);
    }
  });

  it('refuses every scheme that can execute or read the local machine', () => {
    for (const href of [
      'javascript:alert(1)',
      'JaVaScRiPt:alert(1)',
      'vbscript:msgbox(1)',
      'data:text/html,<script>alert(1)</script>',
      'blob:https://example.test/1234',
      'file:///etc/passwd',
      // Not a scheme this application has any use for, and an allowlist refuses by default.
      'ftp://example.test/x',
    ]) {
      expect(isSafeHref(href), href).toBe(false);
    }
  });

  it('strips what a browser strips before it resolves the scheme', () => {
    /*
     * The whole reason the check is not `startsWith('javascript:')`: a browser ignores leading
     * whitespace and control characters, and ignores them *inside* the scheme too, so each of these
     * navigates to `javascript:alert(1)` while reading as a relative path to a naive comparison.
     */
    for (const href of [
      '  javascript:alert(1)',
      '\tjavascript:alert(1)',
      '\njavascript:alert(1)',
      'java\nscript:alert(1)',
      'java\tscript:alert(1)',
      'java\rscript:alert(1)',
      `javascript${ctrl(0)}:alert(1)`,
      `java${ctrl(1)}script:alert(1)`,
      `${ctrl(11)}javascript:alert(1)`,
    ]) {
      expect(isSafeHref(href), JSON.stringify(href)).toBe(false);
    }

    // Stripping cuts the other way too: a padded real URL is still that URL.
    expect(isSafeHref('  https://example.test  ')).toBe(true);
  });

  it('refuses a protocol-relative URL, which is a scheme this app never chooses', () => {
    /*
     * `//evil.test` inherits the page's scheme and is an off-site navigation that looks like a path.
     * A single leading slash is a route; two are a host, and a payload has no business supplying one.
     */
    expect(isSafeHref('//evil.test/phish')).toBe(false);
    expect(isSafeHref('/evil.test/phish')).toBe(true);
  });

  it('refuses an empty href rather than treating it as the current page', () => {
    expect(isSafeHref('')).toBe(false);
    expect(isSafeHref('   ')).toBe(false);
  });
});
