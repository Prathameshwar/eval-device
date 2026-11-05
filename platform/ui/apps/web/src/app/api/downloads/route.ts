import { ApiError, apiBaseUrl } from '@/lib/api';
import { downloadSession } from '@/lib/downloads';

export const dynamic = 'force-dynamic';

async function transfer(request: Request) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const { token } = await downloadSession();
    const params = new URL(request.url).searchParams;
    const artifact = params.get('artifact');
    if (artifact !== 'desktop-cuda' && artifact !== 'desktop-runtime' && artifact !== 'desktop-cpu') throw new ApiError(404, 'not_found');
    const sha256 = params.get('sha256');
    if (sha256 !== null && !/^[a-f0-9]{64}$/.test(sha256)) throw new ApiError(400, 'invalid_release');
    const headers: Record<string, string> = { Authorization: 'Bearer ' + token };
    for (const key of ['Range', 'If-Range']) {
      const value = request.headers.get(key);
      if (value && value.length <= 256) headers[key] = value;
      else if (value) throw new ApiError(400, 'invalid_range');
    }
    const connect = new AbortController();
    timer = setTimeout(() => connect.abort(), 15000);
    const upstream = await fetch(apiBaseUrl() + '/downloads/' + artifact + (sha256 ? '?sha256=' + sha256 : ''), {
      method: request.method, headers, cache: 'no-store', redirect: 'error',
      signal: AbortSignal.any([request.signal, connect.signal]),
    });
    clearTimeout(timer);
    if (!upstream.ok && upstream.status !== 416) {
      await upstream.body?.cancel();
      throw new ApiError(upstream.status, 'download_unavailable');
    }
    const responseHeaders = new Headers({ 'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff', 'X-Accel-Buffering': 'no' });
    for (const key of ['Content-Type', 'Content-Disposition', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified']) {
      const value = upstream.headers.get(key);
      if (value) responseHeaders.set(key, value);
    }
    return new Response(request.method === 'HEAD' ? null : upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 503;
    const message = status === 401 ? 'Your session has expired. Sign in and try again.'
      : status === 403 ? 'Administrator access is required to download this app.'
      : status === 409 ? 'This release has changed. Refresh Downloads and start a new download.'
      : status === 404 ? 'This download was not found. Refresh Downloads and try again.'
      : status === 400 ? 'The download request is invalid. Refresh Downloads and try again.'
      : 'Downloads are temporarily unavailable. Please try again shortly.';
    return new Response(request.method === 'HEAD' ? null : JSON.stringify({ error: message }),
      { status, headers: { 'Cache-Control': 'private, no-store', 'Content-Type': 'application/json',
        'X-Content-Type-Options': 'nosniff' } });
  } finally {
    clearTimeout(timer);
  }
}

export const GET = transfer;
export const HEAD = transfer;
