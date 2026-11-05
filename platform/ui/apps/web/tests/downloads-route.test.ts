import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { GET, HEAD } from '../src/app/api/downloads/route';
import { downloadSession } from '../src/lib/downloads';
import { ApiError } from '../src/lib/api';
import { canDownload } from '../src/lib/download-access';

vi.mock('../src/lib/downloads', () => ({ downloadSession: vi.fn() }));
vi.mock('../src/lib/api', () => ({ apiBaseUrl: () => 'https://api.test/api/v1',
  ApiError: class extends Error { constructor(public status: number, message: string) { super(message); } } }));
const request = (headers?: HeadersInit, method = 'GET') => new Request('https://web.test/api/downloads?artifact=desktop-cpu', { headers, method });
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal('AbortSignal', { any: (signals: AbortSignal[]) => signals[0] });
  vi.mocked(downloadSession).mockResolvedValue({ token: 'fixture-token' } as never);
});
afterEach(() => vi.unstubAllGlobals());

it('streams a resumed download with safe headers and server-only authentication', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('PK', { status: 206, headers: {
    'Content-Type': 'application/zip', 'Content-Range': 'bytes 10-11/100', 'Accept-Ranges': 'bytes',
    'Content-Disposition': 'attachment; filename="portable.zip"', 'Set-Cookie': 'ignored-secret',
  } }));
  vi.stubGlobal('fetch', fetcher);
  const incoming = request({ Range: 'bytes=10-', 'If-Range': '"release-hash"' });
  expect(incoming.headers.get('Range')).toBe('bytes=10-');
  const result = await GET(incoming);
  expect(result.status).toBe(206);
  expect(await result.text()).toBe('PK');
  expect(result.headers.get('Content-Range')).toBe('bytes 10-11/100');
  expect(result.headers.get('Set-Cookie')).toBeNull();
  expect(result.headers.get('X-Accel-Buffering')).toBe('no');
  expect(result.headers.get('Cache-Control')).toContain('no-store');
  const sent = fetcher.mock.calls[0]![1];
  expect(sent.headers.Authorization).toBe('Bearer fixture-token');
  expect(sent.headers.Range).toBe('bytes=10-');
  expect(sent.headers['If-Range']).toBe('"release-hash"');
  expect(sent.redirect).toBe('error');
});

it('forwards HEAD without creating a response body', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { headers: { 'Content-Length': '100' } }));
  vi.stubGlobal('fetch', fetcher);
  const result = await HEAD(request(undefined, 'HEAD'));
  expect(result.body).toBeNull();
  expect(result.headers.get('Content-Length')).toBe('100');
  expect(fetcher.mock.calls[0]![1].method).toBe('HEAD');
});

it('rejects a non-admin before contacting the API', async () => {
  vi.mocked(downloadSession).mockRejectedValue(new ApiError(403, 'permission_denied'));
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  expect((await GET(request())).status).toBe(403);
  expect(fetcher).not.toHaveBeenCalled();
});

it('rejects arbitrary artifact paths and oversized range headers', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  expect((await GET(new Request('https://web.test/api/downloads?artifact=../secret'))).status).toBe(404);
  expect((await GET(request({ Range: 'x'.repeat(257) }))).status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});

it('streams the runtime-only edition with a pinned release through GET and HEAD', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { headers: { 'Content-Disposition': 'attachment; filename="Desktop-App.zip"' } }));
  vi.stubGlobal('fetch', fetcher);
  const url = 'https://web.test/api/downloads?artifact=desktop-runtime&sha256=' + 'a'.repeat(64);
  expect((await GET(new Request(url))).status).toBe(200);
  const head = await HEAD(new Request(url, { method: 'HEAD' }));
  expect(head.body).toBeNull();
  expect(head.headers.get('Content-Disposition')).toContain('Desktop-App.zip');
  expect(fetcher.mock.calls[0]![0]).toContain('/downloads/desktop-runtime?sha256=');
});

it('preserves API denial and invalid range statuses without leaking private errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private details', { status: 403 })));
  const result = await GET(request());
  expect(result.status).toBe(403);
  expect(await result.text()).not.toContain('private details');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 416, headers: { 'Content-Range': 'bytes */100' } })));
  expect((await GET(request())).status).toBe(416);
});

it('permits active admin contexts and hides downloads from regular users', () => {
  expect(canDownload({ role: 'org_user', contexts: [] } as never)).toBe(false);
  expect(canDownload({ role: 'org_admin' } as never)).toBe(true);
  expect(canDownload({ role: 'platform_admin' } as never)).toBe(true);
  expect(canDownload({ role: 'platform_admin', needsAccess: true } as never)).toBe(false);
  expect(canDownload({ role: 'org_user', contexts: [{ role: 'org_admin', department_id: null }] } as never)).toBe(true);
  expect(canDownload({ role: 'org_user', contexts: [{ role: 'org_admin', department_id: 'department' }] } as never)).toBe(false);
  expect(canDownload({ role: 'org_admin', contexts: [{ role: 'org_admin', department_id: 'department' }] } as never)).toBe(false);
});

it('pins the requested release and rejects invalid digests before fetching', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('PK'));
  vi.stubGlobal('fetch', fetcher);
  const digest = 'a'.repeat(64);
  expect((await GET(new Request('https://web.test/api/downloads?artifact=desktop-cpu&sha256=' + digest))).status).toBe(200);
  expect(fetcher.mock.calls[0]![0]).toBe('https://api.test/api/v1/downloads/desktop-cpu?sha256=' + digest);
  expect((await GET(new Request('https://web.test/api/downloads?artifact=desktop-cpu&sha256=invalid'))).status).toBe(400);
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it.each([
  [401, 'session has expired'], [403, 'Administrator access'],
  [409, 'release has changed'], [503, 'temporarily unavailable'],
])('gives an accurate safe error for status %s and omits HEAD bodies', async (status, message) => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response('private details', { status }))));
  const result = await GET(request());
  expect(result.status).toBe(status);
  expect(await result.text()).toContain(message);
  const head = await HEAD(request(undefined, 'HEAD'));
  expect(head.status).toBe(status);
  expect(head.body).toBeNull();
});
