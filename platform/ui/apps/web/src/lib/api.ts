/** Server-only transport. No credentials are returned to a client component. */
import 'server-only';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super('The account request could not be completed.');
  }
}

export function apiBaseUrl(): string {
  const url = new URL(process.env.PMS_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1');
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback))
  ) {
    throw new Error('Configure a trusted HTTPS PMS_API_BASE_URL (loopback HTTP is allowed locally).');
  }
  return url.toString().replace(/\/$/, '');
}

export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string; timeoutMs?: number } = {},
): Promise<T> {
  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      method: options.method ?? 'GET',
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(options.timeoutMs ?? 15000),
      headers: {
        Accept: 'application/json',
        ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    if (response.status === 204) return undefined as T;
    const data = await response.json();
    if (!response.ok)
      throw new ApiError(
        response.status,
        typeof data?.error?.code === 'string' ? data.error.code : 'unavailable',
        data?.error?.details,
      );
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(503, 'unavailable');
  }
}

export function accountError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Unable to connect. Please try again.';
  const messages: Record<string, string> = {
    invalid_setup_key: 'The installation key is incorrect. Check the private deployment settings and try again.',
    setup_completed: 'Initial setup is already complete. Sign in with the existing administrator account.',
    setup_unavailable: 'Setup is not enabled. Contact the person managing this installation.',
    invalid_credentials: 'That email address and password do not match an account.',
    invalid_current_password: 'Your current password is incorrect.',
    invalid_password: 'Use 12–1024 characters and avoid common passwords.',
    invalid_action_token: 'This link is invalid, expired, or already used. Request a new link.',
    local_identity_exists: 'That email address cannot be used. Choose another address.',
    invalid_request: 'Check the email address and password requirements.',
    rate_limit: 'Too many attempts. Please wait a few minutes before trying again.',
    local_auth_disabled: 'Password sign-in is unavailable. Contact your administrator.',
    state_conflict: 'The account changed during this request. Please try again.',
  };
  return (
    messages[error.code] ??
    (error.status === 401
      ? 'Your session has ended. Sign in again.'
      : 'The account service is unavailable. Please try again.')
  );
}
