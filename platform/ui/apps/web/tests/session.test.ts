import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest, ApiError } from '../src/lib/api';
import { checkSession, signIn, signOut } from '../src/lib/actions';
import { CONTEXT_COOKIE, currentUser, SESSION_COOKIE, startSession } from '../src/lib/session';
import { sessionUser } from '../src/lib/session-user';

const jar = vi.hoisted(() => ({
  values: new Map<string, string>(), set: vi.fn(), delete: vi.fn(),
}));
vi.mock('next/headers', () => ({
  cookies: async () => ({
    get: (name: string) => jar.values.has(name) ? { value: jar.values.get(name) } : undefined,
    set: jar.set, delete: jar.delete,
  }),
}));
vi.mock('next/navigation', () => ({ redirect: (path: string) => { throw new Error('redirect:' + path); } }));

const token = 'web_' + 't'.repeat(43);
const identity = {
  user: { id: 'user-id', display_name: 'Actual user', email: 'real@example.com', password_management: true },
  contexts: [{ id: 'org-id', name: 'Actual organisation', role: 'org_read_only', department_id: null, permissions: ['org.configuration.read'] }],
};
function response(data: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}
beforeEach(() => {
  jar.values.clear(); jar.set.mockReset(); jar.delete.mockReset();
  vi.stubGlobal('fetch', vi.fn());
  vi.stubEnv('PMS_API_BASE_URL', 'http://127.0.0.1:8000/api/v1');
});

describe('verified browser session', () => {
  it('ignores forged legacy demo cookies without contacting the API', async () => {
    jar.values.set('ae-demo-session', 'platform-admin');
    expect(await currentUser()).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('gets the identity and exact scoped permissions from the API', async () => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockResolvedValue(response(identity));
    const user = await currentUser();
    expect(user).toMatchObject({ name: 'Actual user', role: 'org_user', roleLabel: 'Read only', permissions: ['org.configuration.read'] });
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/v1/auth/context', expect.objectContaining({
      cache: 'no-store', redirect: 'error', headers: expect.objectContaining({ Authorization: 'Bearer ' + token }),
    }));
  });
  it('rejects revoked sessions and preserves an outage as an error', async () => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockResolvedValueOnce(response({ error: { code: 'invalid_token' } }, 401));
    expect(await currentUser()).toBeUndefined();
    vi.mocked(fetch).mockRejectedValueOnce(new Error('private upstream failure'));
    await expect(currentUser()).rejects.toMatchObject({ status: 503 });
    expect(jar.delete).not.toHaveBeenCalled();
    expect(jar.set).not.toHaveBeenCalled();
  });
  it('uses HttpOnly session cookies unless remembering is chosen', async () => {
    await startSession(token, 28800, false);
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, token, { httpOnly: true, sameSite: 'lax', secure: false, path: '/' });
    await startSession(token, 2592000, true);
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, token, expect.objectContaining({ maxAge: 2592000 }));
  });
  it('does not accept a user id as a session token', async () => {
    await expect(startSession('platform-admin', 28800, false)).rejects.toBeInstanceOf(ApiError);
    expect(jar.set).not.toHaveBeenCalled();
  });
  it('keeps platform and tenant grants in separate contexts', () => {
    const platform = { id: 'platform', name: 'Platform', role: 'platform_admin', department_id: null, permissions: ['platform.users.read'] };
    const data = { ...identity, contexts: [platform, ...identity.contexts] };
    expect(sessionUser(data, 'org-id').permissions).toEqual(['org.configuration.read']);
    expect(sessionUser(data, 'forged-org').permissions).toEqual(['platform.users.read']);
    expect(sessionUser({ ...identity, contexts: [] })).toMatchObject({ needsAccess: true, permissions: [] });
  });
});

describe('account server actions', () => {
  it('authenticates through the API and never returns a token to client code', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ session_token: token, expires_in: 28800 }));
    await expect(signIn(' real@example.com ', 'a test password long enough', false)).rejects.toThrow('redirect:/home');
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/v1/auth/browser/login', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ email: 'real@example.com', password: 'a test password long enough', remember: false }),
    }));
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, token, expect.anything());
  });
  it('reports generic credential failures and does not create a cookie', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ error: { code: 'invalid_credentials', message: 'private' } }, 401));
    expect(await signIn('real@example.com', 'wrong')).toEqual({ error: 'That email address and password do not match an account.' });
    expect(jar.set).not.toHaveBeenCalled();
  });
  it('clears browser credentials before attempting bounded API revocation', async () => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockImplementation(async () => {
      expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
      expect(jar.set).toHaveBeenCalledWith(CONTEXT_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
      expect(jar.delete).toHaveBeenCalledWith('ae-demo-session');
      return response(null, 204);
    });
    await expect(signOut()).rejects.toThrow('redirect:/login');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/auth/logout'), expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer ' + token }),
      signal: expect.any(AbortSignal),
    }));
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ httpOnly: true, sameSite: 'lax', secure: false, path: '/', maxAge: 0 }));
  });
  it('signs out locally when revocation cannot reach the API', async () => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockRejectedValue(new Error('private'));
    await expect(signOut()).rejects.toThrow('redirect:/login');
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
    expect(jar.set).toHaveBeenCalledWith(CONTEXT_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
    expect(fetch).toHaveBeenCalledOnce();
  });
  it.each([403, 429, 500, 503])('signs out locally when the API returns %s', async (status) => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockResolvedValue(response({ error: { code: 'unavailable' } }, status));
    await expect(signOut()).rejects.toThrow('redirect:/login');
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
    expect(fetch).toHaveBeenCalledOnce();
  });
  it.each([undefined, 'invalid-token'])('clears cookies without API access for credential %s', async (value) => {
    if (value) jar.values.set(SESSION_COOKIE, value);
    await expect(signOut()).rejects.toThrow('redirect:/login');
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
    expect(jar.set).toHaveBeenCalledWith(CONTEXT_COOKIE, '', expect.objectContaining({ maxAge: 0 }));
    expect(fetch).not.toHaveBeenCalled();
  });
  it('finishes sign-out within two seconds when revocation stalls', async () => {
    vi.useFakeTimers();
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockImplementation((milliseconds) => {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), milliseconds);
      return controller.signal;
    });
    try {
      jar.values.set(SESSION_COOKIE, token);
      vi.mocked(fetch).mockImplementation((_url, options) => new Promise((_resolve, reject) => {
        options!.signal!.addEventListener('abort', () => reject(new Error('timed out')), { once: true });
      }));
      const completed = expect(signOut()).rejects.toThrow('redirect:/login');
      await vi.advanceTimersByTimeAsync(2000);
      await completed;
      expect(fetch).toHaveBeenCalledOnce();
    } finally {
      timeout.mockRestore();
      vi.useRealTimers();
    }
  });
  it('permits clearing a session already revoked by the API', async () => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockResolvedValue(response({ error: { code: 'invalid_token' } }, 401));
    await expect(signOut()).rejects.toThrow('redirect:/login');
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ httpOnly: true, sameSite: 'lax', secure: false, path: '/', maxAge: 0 }));
  });
  it('rechecks an open session, clears revoked credentials, and preserves cookies during outages', async () => {
    jar.values.set(SESSION_COOKIE, token);
    vi.mocked(fetch).mockResolvedValueOnce(response(identity));
    expect(await checkSession()).toBe('active');
    expect(jar.set).not.toHaveBeenCalled();

    vi.mocked(fetch).mockResolvedValueOnce(response({ error: { code: 'invalid_token' } }, 401));
    expect(await checkSession()).toBe('expired');
    expect(jar.set).toHaveBeenCalledWith(SESSION_COOKIE, '', expect.objectContaining({ maxAge: 0 }));

    jar.set.mockClear();
    vi.mocked(fetch).mockRejectedValueOnce(new Error('private upstream failure'));
    expect(await checkSession()).toBe('unavailable');
    expect(jar.set).not.toHaveBeenCalled();
  });
  it('rejects untrusted non-HTTPS API configuration and never retries a mutation', async () => {
    vi.stubEnv('PMS_API_BASE_URL', 'http://untrusted.example/api/v1');
    await expect(apiRequest('/auth/login', { method: 'POST' })).rejects.toMatchObject({ status: 503 });
    expect(fetch).not.toHaveBeenCalled();
    vi.stubEnv('PMS_API_BASE_URL', 'http://127.0.0.1:8000/api/v1');
    vi.mocked(fetch).mockRejectedValue(new Error('uncertain outcome'));
    await expect(apiRequest('/auth/email/confirm', { method: 'POST' })).rejects.toMatchObject({ status: 503 });
    expect(fetch).toHaveBeenCalledOnce();
  });
});
