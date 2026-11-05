import { logoutSession } from '@/lib/session';

/** A native POST also works when the browser has an obsolete server-action bundle. */
export async function POST(request: Request) {
  const url = new URL(request.url);
  // Next's internal URL can contain its bind address. The trusted proxy preserves Host and scheme.
  const host = request.headers.get('host') ?? url.host;
  const protocol = request.headers.get('x-forwarded-proto') ?? url.protocol.slice(0, -1);
  const origin = request.headers.get('origin');
  const site = request.headers.get('sec-fetch-site');
  // The app's no-referrer policy can make native POST Origin null. Fetch Metadata must then prove same-origin.
  const sameOrigin = origin === `${protocol}://${host}` ||
    ((origin === null || origin === 'null') && site === 'same-origin');
  if (!sameOrigin || site === 'cross-site') {
    return new Response('Forbidden', { status: 403, headers: { 'Cache-Control': 'no-store' } });
  }
  await logoutSession();
  return new Response(null, {
    status: 303,
    headers: { Location: '/login', 'Cache-Control': 'private, no-store' },
  });
}
