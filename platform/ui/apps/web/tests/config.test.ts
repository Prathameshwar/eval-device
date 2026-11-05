import { describe, expect, it } from 'vitest';
import createConfig from '../next.config.mjs';
import { PHASE_PRODUCTION_BUILD } from 'next/constants';
const config = createConfig(PHASE_PRODUCTION_BUILD);

/**
 * Two settings that are invisible when present and expensive when absent: the transpile hint the
 * package build depends on, and the response headers a sign-in page owes. Both are one line to
 * delete in a merge, and nothing else in the suite would notice.
 */
describe('next config', () => {
  it('compiles the design system from source', () => {
    expect(config.transpilePackages).toContain('@pms/ui');
  });

  it('serves the sign-in screens with framing and sniffing denied', async () => {
    const groups = await config.headers!();
    const headers = groups.flatMap((group) => group.headers);
    const value = (key: string) => headers.find((header) => header.key === key)?.value;

    expect(groups.map((group) => group.source)).toContain('/:path*');
    expect(value('X-Frame-Options')).toBe('DENY');
    expect(value('X-Content-Type-Options')).toBe('nosniff');
    expect(value('Referrer-Policy')).toBe('no-referrer');
    expect(value('Cross-Origin-Opener-Policy')).toBe('same-origin');
    expect(value('Permissions-Policy')).toMatch(/camera=\(\)/);
    expect(config.poweredByHeader).toBe(false);
  });
});
