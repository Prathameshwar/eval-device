'use server';
import { ApiError, apiRequest } from './api';
import { CLINICAL_CAPABILITIES, type CapabilityAssignment, type ClinicalCapability } from './clinical-capabilities';
import { consoleSession, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult } from './directory-api';

async function access(contextId: string, memberId: string) {
  const { user, token } = await consoleSession('org.members.manage');
  if (user.contextId !== contextId || contextId === 'platform')
    throw new ApiError(403, 'permission_denied');
  return { token, path: '/organizations/' + resourceId(contextId) +
    '/members/' + resourceId(memberId) + '/capabilities' };
}
export async function listCapabilities(contextId: string, memberId: string):
  Promise<ApiResult<CapabilityAssignment[]>> {
  try {
    const { token, path } = await access(contextId, memberId);
    const result = await apiRequest<{ items: CapabilityAssignment[] }>(path, { token });
    return { value: result.items };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function setCapability(contextId: string, memberId: string,
  capability: ClinicalCapability, enabled: boolean): Promise<ApiResult<CapabilityAssignment | boolean>> {
  try {
    if (!CLINICAL_CAPABILITIES.some(([code]) => code === capability))
      throw new ApiError(422, 'invalid_capability');
    const { token, path } = await access(contextId, memberId);
    if (enabled) return { value: await apiRequest<CapabilityAssignment>(path,
      { token, method: 'POST', body: { capability } }) };
    await apiRequest(path + '/' + capability, { token, method: 'DELETE' });
    return { value: true };
  } catch (error) { return { error: consoleError(error) }; }
}
