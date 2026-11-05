'use server';
import { ApiError, apiRequest } from './api';
import { currentUser, sessionToken } from './session';
import { consoleError } from './console-errors';
import type { ApiResult } from './directory-api';
export type PersonalProfile = {
  display_name: string;
  email: string;
  phone: string | null;
  auth_method: string;
};
async function token() {
  if (!(await currentUser())) throw new ApiError(401, 'authentication_required');
  return sessionToken();
}
export async function readPersonal(): Promise<ApiResult<PersonalProfile>> {
  try {
    const r = await apiRequest<{ user: PersonalProfile }>('/me', {
      token: await token(),
    });
    return { value: r.user };
  } catch (e) {
    return { error: consoleError(e) };
  }
}
export async function savePersonal(display_name: string, phone: string): Promise<ApiResult<PersonalProfile>> {
  try {
    const auth = await token();
    if (!display_name.trim()) return { error: 'Enter your display name.' };
    return {
      value: await apiRequest<PersonalProfile>('/me', {
        token: auth,
        method: 'PATCH',
        body: {
          display_name: display_name.trim(),
          phone: phone.trim() || null,
        },
      }),
    };
  } catch (e) {
    return { error: consoleError(e) };
  }
}
