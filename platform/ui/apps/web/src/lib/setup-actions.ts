'use server';

import { accountError, apiRequest, ApiError } from './api';

export type SetupResult = { completed?: boolean; error?: string; code?: string };
export type SetupDetails = { display_name: string; email: string; password: string; installation_key: string };

function failure(error: unknown): SetupResult {
  return { error: accountError(error), code: error instanceof ApiError ? error.code : 'unavailable' };
}

export async function verifyInstallationKey(key: string): Promise<SetupResult> {
  if (typeof key !== 'string' || !key || key.length > 512) return { error: 'Enter a valid installation key.' };
  try {
    await apiRequest('/auth/setup/verify', { method: 'POST', body: { installation_key: key } });
    return { completed: true };
  } catch (error) {
    if (error instanceof ApiError && error.code === 'invalid_request') {
      return { error: 'Enter a valid installation key.', code: 'invalid_setup_key' };
    }
    return failure(error);
  }
}

export async function completeInitialSetup(details: SetupDetails): Promise<SetupResult> {
  if (!details || typeof details !== 'object' ||
      typeof details.display_name !== 'string' || !details.display_name.trim() || details.display_name.length > 256 ||
      typeof details.email !== 'string' || !details.email.trim() || details.email.length > 320 ||
      typeof details.password !== 'string' || details.password.length < 12 || details.password.length > 1024 ||
      typeof details.installation_key !== 'string' || !details.installation_key || details.installation_key.length > 512) {
    return { error: 'Check the administrator details and password requirements.' };
  }
  try {
    return await apiRequest<SetupResult>('/auth/setup', { method: 'POST', body: {
      display_name: details.display_name.trim(), email: details.email.trim(),
      password: details.password, installation_key: details.installation_key,
    } });
  } catch (error) { return failure(error); }
}
