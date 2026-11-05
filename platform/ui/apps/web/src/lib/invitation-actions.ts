'use server';
import { accountError, apiRequest } from './api';
import { consoleError } from './console-errors';
import { sessionToken, setContext, startSession } from './session';
import type { ApiResult } from './directory-api';

export async function joinInvitation(invitation: string, credentials?: { email: string; password: string }): Promise<ApiResult<true>> {
  if (typeof invitation !== 'string' || !/^inv_[A-Za-z0-9_-]{20,252}$/.test(invitation)) return { error: 'This invitation link is invalid.' };
  if (credentials) {
    if (typeof credentials.email !== 'string' || typeof credentials.password !== 'string' || credentials.email.length > 320 || !credentials.password || credentials.password.length > 1024) return { error: 'Enter your email and password.' };
    try {
      const login = await apiRequest<{ session_token: string; expires_in: number }>('/auth/browser/login', { method: 'POST', body: { email: credentials.email.trim(), password: credentials.password, remember: false } });
      await startSession(login.session_token, login.expires_in, false);
    } catch (error) { return { error: accountError(error) }; }
  }
  try {
    const token = await sessionToken();
    if (!token) return { error: 'Sign in with the account that received the invitation.' };
    const result = await apiRequest<{ organization_id: string }>('/invitations/accept', { token, method: 'POST', body: { token: invitation } });
    await setContext(result.organization_id);
    return { value: true };
  } catch (error) { return { error: consoleError(error) }; }
}
