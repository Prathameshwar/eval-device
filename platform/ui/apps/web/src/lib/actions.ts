'use server';

import { redirect } from 'next/navigation';
import { accountError, apiRequest } from './api';
import { currentUser, endSession, logoutSession, sessionToken, setContext, startSession } from './session';

export type AccountResult = { error?: string; completed?: boolean };
export type SignInResult = { error: string };

export async function signIn(email: string, password: string, remember = false): Promise<SignInResult | void> {
  try {
    if (typeof email !== 'string' || typeof password !== 'string' || typeof remember !== 'boolean' ||
        email.length > 320 || password.length < 1 || password.length > 1024) {
      return { error: 'Enter a valid email address and password.' };
    }
    const result = await apiRequest<{ session_token: string; expires_in: number }>('/auth/browser/login', {
      method: 'POST', body: { email: email.trim(), password, remember },
    });
    await startSession(result.session_token, result.expires_in, remember);
  } catch (error) {
    return { error: accountError(error) };
  }
  redirect('/home');
}

export async function signOut(): Promise<void> {
  await logoutSession();
  redirect('/login');
}

/** Recheck the server-side session for open tabs without exposing its cookie to client code. */
export async function checkSession(): Promise<'active' | 'expired' | 'unavailable'> {
  try {
    if (await currentUser()) return 'active';
    await endSession();
    return 'expired';
  } catch {
    // An API outage must not silently sign a user out.
    return 'unavailable';
  }
}

export async function forgotPassword(email: string): Promise<AccountResult> {
  try {
    await apiRequest('/auth/password/forgot', { method: 'POST', body: { email } });
    return { completed: true };
  } catch (error) { return { error: accountError(error) }; }
}

export async function completeAccountAction(purpose: string, token: string, password?: string): Promise<AccountResult> {
  const paths: Record<string, string> = { setup: '/auth/password/setup', 'password-reset': '/auth/password/reset', 'email-change': '/auth/email/confirm' };
  if (typeof purpose !== 'string' || !Object.prototype.hasOwnProperty.call(paths, purpose) || typeof token !== 'string' || token.length > 512) {
    return { error: 'This account link is invalid.' };
  }
  try {
    await apiRequest(paths[purpose]!, { method: 'POST', body: purpose === 'email-change' ? { token } : { token, password } });
    await endSession();
    return { completed: true };
  } catch (error) { return { error: accountError(error) }; }
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<AccountResult> {
  try {
    const token = await sessionToken();
    if (!token) return { error: 'Your session has ended. Sign in again.' };
    await apiRequest('/auth/password/change', { method: 'POST', token, body: { current_password: currentPassword, new_password: newPassword } });
    await endSession();
    return { completed: true };
  } catch (error) { return { error: accountError(error) }; }
}

export async function changeEmail(email: string, currentPassword: string): Promise<AccountResult> {
  try {
    const token = await sessionToken();
    if (!token) return { error: 'Your session has ended. Sign in again.' };
    await apiRequest('/auth/email/change', { method: 'POST', token, body: { email, current_password: currentPassword } });
    return { completed: true };
  } catch (error) { return { error: accountError(error) }; }
}

export async function switchContext(id: string): Promise<AccountResult | void> {
  try {
    const user = await currentUser();
    if (!user?.contexts?.some((context) => context.id === id)) return { error: 'This account no longer has access to that organisation.' };
    await setContext(id);
  } catch (error) { return { error: accountError(error) }; }
  redirect('/home');
}
