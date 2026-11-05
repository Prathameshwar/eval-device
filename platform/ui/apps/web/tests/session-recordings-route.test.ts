import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { GET } from '../src/app/api/session-recordings/route';
import { consoleSession } from '../src/lib/console-api';

vi.mock('../src/lib/console-api', () => ({ consoleSession: vi.fn(), resourceId: (value: string) => {
  if (!/^[a-f0-9-]{36}$/.test(value)) throw new Error('invalid id'); return value;
} }));
vi.mock('../src/lib/api', () => ({ apiBaseUrl: () => 'https://api.test/api/v1',
  ApiError: class extends Error { constructor(public status: number, message: string) { super(message); } } }));
const org = '11111111-1111-4111-8111-111111111111';
const archive = '22222222-2222-4222-8222-222222222222';
const item = '33333333-3333-4333-8333-333333333333';
const request = () => new Request(`https://web.test/api/session-recordings?context=${org}&archive=${archive}&item=${item}`);
beforeEach(() => {
  vi.resetAllMocks();
  // JSDOM's AbortSignal lacks the server runtime's any()/timeout() methods.
  vi.stubGlobal('AbortSignal', { any: (signals: AbortSignal[]) => signals[0], timeout: () => new AbortController().signal });
  vi.mocked(consoleSession).mockResolvedValue({ token: 'fixture-token', user: { contextId: org } } as never);
});
afterEach(() => vi.unstubAllGlobals());
it('streams the authorized response and forwards only safe media headers', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('fixture audio', { headers: {
    'Content-Type': 'audio/wav', 'Content-Disposition': 'attachment; filename="audio.wav"', 'Set-Cookie': 'secret=ignored',
  } }));
  vi.stubGlobal('fetch', fetcher);
  const result = await GET(request());
  expect(result.status).toBe(200);
  expect(await result.text()).toBe('fixture audio');
  expect(result.headers.get('Set-Cookie')).toBeNull();
  expect(result.headers.get('Cache-Control')).toContain('no-store');
  expect(consoleSession).toHaveBeenCalledWith('org.results.read');
  expect(fetcher).toHaveBeenCalledWith(`https://api.test/api/v1/organizations/${org}/session-archives/${archive}/items/${item}`,
    expect.objectContaining({ cache: 'no-store', redirect: 'error', headers: { Authorization: 'Bearer fixture-token' } }));
});
it('rejects a changed organization context before contacting the API', async () => {
  vi.mocked(consoleSession).mockResolvedValue({ token: 'fixture-token', user: { contextId: archive } } as never);
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  expect((await GET(request())).status).toBe(409);
  expect(fetcher).not.toHaveBeenCalled();
});
it('preserves upstream denial without exposing upstream response contents', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('private provider details', { status: 403 })));
  const result = await GET(request());
  expect(result.status).toBe(403);
  expect(await result.text()).not.toContain('private provider details');
});
