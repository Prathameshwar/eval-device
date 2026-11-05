import 'server-only';
import { cache } from 'react';
import { cookies } from 'next/headers';
import { apiRequest, ApiError } from './api';
import { sessionUser, type IdentityContext } from './session-user';

export const SESSION_COOKIE = process.env.NODE_ENV === 'production' ? '__Host-ae-session' : 'ae-session';
export const CONTEXT_COOKIE = process.env.NODE_ENV === 'production' ? '__Host-ae-context' : 'ae-context';
const COOKIE_OPTIONS = { httpOnly: true, sameSite: 'lax' as const, secure: process.env.NODE_ENV === 'production', path: '/' };

export async function sessionToken(): Promise<string | undefined> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return token && /^web_[A-Za-z0-9_-]{32,128}$/.test(token) ? token : undefined;
}

export const currentUser = cache(async () => {
  const token = await sessionToken();
  if (!token) return undefined;
  try {
    const identity = await apiRequest<IdentityContext>('/auth/context', { token });
    return sessionUser(identity, (await cookies()).get(CONTEXT_COOKIE)?.value);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return undefined;
    throw error;
  }
});

export async function startSession(token: string, expiresIn: number, remember: boolean): Promise<void> {
  if (!/^web_[A-Za-z0-9_-]{32,128}$/.test(token) || !Number.isInteger(expiresIn) || expiresIn <= 0 || expiresIn > 90 * 86400) {
    throw new ApiError(503, 'unavailable');
  }
  const store = await cookies();
  store.set(SESSION_COOKIE, token, { ...COOKIE_OPTIONS, ...(remember ? { maxAge: expiresIn } : {}) });
  store.set(CONTEXT_COOKIE, '', { ...COOKIE_OPTIONS, maxAge: 0 });
  store.delete('ae-demo-session');
}

export async function endSession(): Promise<void> {
  const store = await cookies();
  // Prefix cookies must retain Secure and Path=/ even when expiring them.
  store.set(SESSION_COOKIE, '', { ...COOKIE_OPTIONS, maxAge: 0 });
  store.set(CONTEXT_COOKIE, '', { ...COOKIE_OPTIONS, maxAge: 0 });
  store.delete('ae-demo-session');
}

/** Explicit sign-out always clears this browser; unavailable API revocation must not block it. */
export async function logoutSession(): Promise<void> {
  const token = await sessionToken();
  await endSession();
  if (!token) return;
  try {
    await apiRequest('/auth/logout', { method: 'POST', token, timeoutMs: 2000 });
  } catch {
    // One best-effort revocation only. The local credential has already been removed.
  }
}

export async function setContext(id: string): Promise<void> {
  (await cookies()).set(CONTEXT_COOKIE, id, COOKIE_OPTIONS);
}
