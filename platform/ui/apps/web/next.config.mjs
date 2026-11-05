import nextConstants from 'next/constants.js';

const { PHASE_DEVELOPMENT_SERVER } = nextConstants;

/**
 * `@pms/ui` publishes TypeScript source rather than a build (see its `package.json` `exports`),
 * which is the whole reason `transpilePackages` is here: without it Next hands `.tsx` from
 * `node_modules` straight to the bundler and the build fails on the first type annotation. The
 * package's README states the same requirement for any consuming app.
 *
 * Authentication uses server actions and the server-only API adapter in src/lib/api.ts.
 */

/**
 * The headers a sign-in page owes regardless of whether it yet signs anyone in — a framed login
 * form is a credential-harvesting page with the real one behind it, and these cost nothing now
 * while being easy to forget once there is a session to protect.
 *
 * There is deliberately **no** `Content-Security-Policy` here. A useful one has to allow the
 * pre-paint theme script, and the only safe way to do that is a per-request nonce from
 * middleware; a policy with `'unsafe-inline'` would be a CSP in name only. That is tracked with
 * the rest of the sign-in work rather than faked here.
 */
const SECURITY_HEADERS = [
  /* `frame-ancestors` in a CSP supersedes this, and until there is a CSP this is the only
   * clickjacking defence. */
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  /* An email address can end up in a query string on a form screen; no referrer means it cannot
   * leak to a third party through one. */
  { key: 'Referrer-Policy', value: 'no-referrer' },
  /* Nothing on these screens uses a device. Denying by name is what keeps an embedded widget
   * added later from inheriting permission by default. */
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=()' },
  { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@pms/ui'],
  /* `poweredByHeader` states the framework and version to anyone scanning; it buys nothing. */
  poweredByHeader: false,
  async headers() {
    return [{ source: '/:path*', headers: SECURITY_HEADERS }];
  },
};

/** @param {string} phase */
export default function config(phase) {
  // A build or a second dev server must never overwrite a running UI's chunks.
  const instance = process.env.PMS_WEB_INSTANCE ?? 'default';
  if (!/^[a-zA-Z0-9_-]{1,40}$/.test(instance)) throw new Error('Invalid PMS_WEB_INSTANCE.');
  return {
    ...nextConfig,
    distDir: phase === PHASE_DEVELOPMENT_SERVER ? `.next-dev-${instance}` : '.next',
  };
}
