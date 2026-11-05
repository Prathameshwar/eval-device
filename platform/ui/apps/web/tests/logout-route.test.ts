import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { POST } from '../src/app/logout/route';
import { CONTEXT_COOKIE, currentUser, SESSION_COOKIE } from '../src/lib/session';

const jar = vi.hoisted(() => ({
  values: new Map<string, string>(), set: vi.fn(), delete: vi.fn(),
}));
vi.mock('next/headers', () => ({
  cookies: async () => ({
    get: (name: string) => ({ value: jar.values.get(name) }), set: jar.set, delete: jar.delete,
  }),
}));
const token = 'web_' + 't'.repeat(43);
const origin = 'http://localhost:3000';
beforeEach(() => {
  jar.values.clear();
  jar.set.mockReset().mockImplementation((name: string, value: string) => jar.values.set(name, value));
  jar.delete.mockReset();
  jar.values.set(SESSION_COOKIE, token);
  jar.values.set(CONTEXT_COOKIE, 'tenant-a');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
  vi.stubEnv('PMS_API_BASE_URL', 'http://127.0.0.1:8000/api/v1');
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
function request(headers: Record<string, string> = { Origin: origin }) {
  return new Request(origin + '/logout', { method: 'POST', headers });
}

it.each(['healthy', 'unavailable'])('clears the session and redirects with a %s API', async (state) => {
  if (state === 'unavailable') vi.mocked(fetch).mockRejectedValue(new Error('private upstream failure'));
  const result = await POST(request());
  expect(result.status).toBe(303);
  expect(result.headers.get('Location')).toBe('/login');
  expect(result.headers.get('Cache-Control')).toBe('private, no-store');
  expect(await result.text()).toBe('');
  expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0, httpOnly: true }));
  expect(jar.set).toHaveBeenCalledWith(CONTEXT_COOKIE, '', expect.objectContaining({ maxAge: 0, httpOnly: true }));
  expect(jar.delete).toHaveBeenCalledWith('ae-demo-session');
  expect(fetch).toHaveBeenCalledOnce();
  expect(await currentUser()).toBeUndefined();
  expect(fetch).toHaveBeenCalledOnce();
});

const untrustedHeaders: Record<string, string>[] = [
  {},
  { Origin: 'null' },
  { Origin: 'http://attacker.test' },
  { Origin: 'https://localhost:3000' },
  { Origin: 'http://localhost:3001' },
  { Origin: origin, 'Sec-Fetch-Site': 'cross-site' },
];
it.each(untrustedHeaders)('rejects an untrusted POST without clearing credentials: %j', async (headers) => {
  const result = await POST(request(headers));
  expect(result.status).toBe(403);
  expect(jar.set).not.toHaveBeenCalled();
  expect(jar.delete).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

it('retains Secure and Path=/ when expiring production prefix cookies', async () => {
  vi.stubEnv('NODE_ENV', 'production');
  vi.resetModules();
  const route = await import('../src/app/logout/route');
  jar.values.set('__Host-ae-session', token);
  vi.mocked(fetch).mockRejectedValue(new Error('private upstream failure'));
  expect((await route.POST(request())).status).toBe(303);
  for (const name of ['__Host-ae-session', '__Host-ae-context']) {
    expect(jar.set).toHaveBeenCalledWith(name, '', {
      httpOnly: true, sameSite: 'lax', secure: true, path: '/', maxAge: 0,
    });
  }
});

it('accepts the public HTTPS origin behind the trusted proxy', async () => {
  const result = await POST(new Request('http://127.0.0.1:3000/logout', {
    method: 'POST', headers: {
      Host: 'console.example.test', Origin: 'https://console.example.test',
      'X-Forwarded-Proto': 'https', 'Sec-Fetch-Site': 'same-origin',
    },
  }));
  expect(result.status).toBe(303);
  expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
});

it('does not trust an arbitrary forwarded host to authorize sign-out', async () => {
  const result = await POST(request({
    Host: 'console.example.test', Origin: 'https://attacker.test',
    'X-Forwarded-Host': 'attacker.test', 'X-Forwarded-Proto': 'https',
  }));
  expect(result.status).toBe(403);
  expect(jar.set).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

it.each([null, 'null'])('accepts a native same-origin POST under no-referrer with Origin %s', async (originHeader) => {
  const headers: Record<string, string> = { 'Sec-Fetch-Site': 'same-origin' };
  if (originHeader) headers.Origin = originHeader;
  expect((await POST(request(headers))).status).toBe(303);
  expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
});

it.each(['same-site', 'none'])('rejects opaque-origin sign-out for Fetch Metadata %s', async (site) => {
  expect((await POST(request({ Origin: 'null', 'Sec-Fetch-Site': site }))).status).toBe(403);
  expect(jar.set).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});
