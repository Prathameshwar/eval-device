import { ApiError, apiBaseUrl } from '@/lib/api';
import { consoleSession, resourceId } from '@/lib/console-api';

export async function GET(request: Request) {
  try {
    const query = new URL(request.url).searchParams;
    const org = resourceId(query.get('context') ?? '');
    const archive = resourceId(query.get('archive') ?? '');
    const item = resourceId(query.get('item') ?? '');
    const session = await consoleSession('org.results.read');
    if (session.user.contextId !== org) throw new ApiError(409, 'context_changed');
    const upstream = await fetch(apiBaseUrl() + '/organizations/' + org + '/session-archives/' + archive + '/items/' + item, {
      headers: { Authorization: 'Bearer ' + session.token }, cache: 'no-store', redirect: 'error',
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(600000)]),
    });
    if (!upstream.ok) throw new ApiError(upstream.status, 'recording_unavailable');
    const headers = new Headers({ 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff' });
    for (const key of ['Content-Type', 'Content-Disposition', 'Content-Length']) {
      const value = upstream.headers.get(key); if (value) headers.set(key, value);
    }
    return new Response(upstream.body, { headers });
  } catch (error) {
    return Response.json({ error: 'Recording is not available. Refresh the session and try again.' },
      { status: error instanceof ApiError ? error.status : 503, headers: { 'Cache-Control': 'no-store' } });
  }
}
