'use server';
import { ApiError, apiRequest } from './api';
import { consoleSession } from './console-api';
import { consoleError } from './console-errors';
import { inputIssues } from './input-errors';
import type { ApiResult } from './directory-api';
import type { LanguageOption } from './patient-catalog';
export type PlatformOptions = {
  configuration_version: number;
  display_name: string;
  registration_mode: 'self_service' | 'invite_only';
  languages: LanguageOption[];
  enabled_providers: string[];
  maintenance_mode: boolean;
};
async function access(manage = false) {
  const s = await consoleSession(manage ? 'platform.settings.manage' : 'platform.settings.read');
  if (s.user.contextId !== 'platform') throw new ApiError(403, 'permission_denied');
  return s;
}
export async function readPlatformOptions(): Promise<ApiResult<PlatformOptions>> {
  try {
    const { token } = await access();
    return {
      value: await apiRequest<PlatformOptions>('/platform/settings', { token }),
    };
  } catch (e) {
    if (e instanceof ApiError && ['integrity_conflict', 'constraint_violation'].includes(e.code))
      return {
        error:
          'These options conflict with existing configuration. Keep English active and retain languages assigned to devices.',
      };
    return {
      error: [consoleError(e), inputIssues(e)].filter(Boolean).join(' '),
    };
  }
}
export async function savePlatformOptions(options: PlatformOptions): Promise<ApiResult<PlatformOptions>> {
  try {
    const { token } = await access(true);
    if (!options.languages.some((l) => l.code === 'en' && l.is_active !== false))
      return {
        error: 'Keep English (en) active as the default device language.',
      };
    return {
      value: await apiRequest<PlatformOptions>('/platform/settings', {
        token,
        method: 'PATCH',
        body: {
          expected_version: options.configuration_version,
          display_name: options.display_name,
          registration_mode: options.registration_mode,
          languages: options.languages,
          enabled_providers: options.enabled_providers,
          maintenance_mode: options.maintenance_mode,
        },
      }),
    };
  } catch (e) {
    if (e instanceof ApiError && ['integrity_conflict', 'constraint_violation'].includes(e.code))
      return {
        error:
          'These options conflict with existing configuration. Keep English active and retain languages assigned to devices.',
      };
    return {
      error: [consoleError(e), inputIssues(e)].filter(Boolean).join(' '),
    };
  }
}
