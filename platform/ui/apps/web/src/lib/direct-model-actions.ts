'use server';
import { revalidatePath } from 'next/cache';
import { ApiError, apiRequest } from './api';
import { consoleSession, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult } from './directory-api';
import type { DeviceChoices, ModelDraft, ModelTestResult, RuntimeModel, Selection, SelectionDraft } from './direct-model-types';

async function access(permission: string) {
  const { user, token } = await consoleSession(permission);
  if (user.contextId !== 'platform' || user.role !== 'platform_admin') throw new ApiError(403, 'permission_denied');
  return token;
}
export async function listModels(): Promise<ApiResult<RuntimeModel[]>> {
  try { const token = await access('platform.settings.manage');
    const result = await apiRequest<{ items: RuntimeModel[] }>('/platform/runtime-models', { token });
    return { value: result.items };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function saveModel(draft: ModelDraft, id?: string): Promise<ApiResult<RuntimeModel> & { uncertain?: boolean }> {
  try { const token = await access('platform.settings.manage');
    const value = await apiRequest<RuntimeModel>('/platform/runtime-models' + (id ? '/' + resourceId(id) : ''), { token, method: id ? 'PUT' : 'POST', body: draft });
    revalidatePath('/models'); revalidatePath('/devices'); return { value };
  } catch (error) {
    const uncertain = error instanceof ApiError && error.code === "unavailable";
    return { error: uncertain ? "Unable to confirm the save. Reload before trying again." : consoleError(error), uncertain };
  }
}
export async function deleteModel(id: string, revision: number): Promise<ApiResult<{ deleted: boolean }>> {
  try { const token = await access('platform.settings.manage');
    const value = await apiRequest<{ deleted: boolean }>(`/platform/runtime-models/${resourceId(id)}?expected_revision=${revision}`, { token, method: 'DELETE' });
    revalidatePath('/models'); return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function testModel(id: string, revision: number): Promise<ApiResult<ModelTestResult>> {
  try { const token = await access('platform.settings.manage');
    const value = await apiRequest<ModelTestResult>(`/platform/runtime-models/${resourceId(id)}/test`, {
      token, method: 'POST', body: { expected_revision: revision }, timeoutMs: 40000,
    });
    if (value.status === 'failed') return { error: consoleError(new ApiError(502, value.error_code ?? 'model_test_failed')) };
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function deviceModels(deviceId: string): Promise<ApiResult<DeviceChoices>> {
  try { const token = await access('platform.organizations.manage');
    return { value: await apiRequest<DeviceChoices>(`/platform/devices/${resourceId(deviceId)}/models`, { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function saveDeviceModels(deviceId: string, body: SelectionDraft): Promise<ApiResult<Selection> & { uncertain?: boolean }> {
  try { const token = await access('platform.organizations.manage');
    const value = await apiRequest<Selection>(`/platform/devices/${resourceId(deviceId)}/models`, { token, method: 'PUT', body });
    revalidatePath('/devices'); return { value };
  } catch (error) {
    const uncertain = error instanceof ApiError && error.code === "unavailable";
    return { error: uncertain ? "Unable to confirm the save. Reload before trying again." : consoleError(error), uncertain };
  }
}
