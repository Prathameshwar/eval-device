'use server';
import { revalidatePath } from 'next/cache';
import { ApiError, apiRequest } from './api';
import { currentUser, sessionToken } from './session';
import { queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import type { ModelDefinition, ModelQuery } from './model-directory';
import type { ModelDraft } from './model-editor';

export type ProviderOption = { id: string; operations: string[]; adapterAvailable: boolean };

/**
 * The catalog has two readers: the platform view (`/platform/models`) sees every lifecycle,
 * including retired definitions, and is the only view that can write. The tenant-facing view
 * (`/models`) is read-only and never returns retired rows. `manage` always requires the former.
 */
async function access(manage = false) {
  const user = await currentUser();
  if (!user) throw new ApiError(401, 'authentication_required');
  if (manage) {
    if (!user.permissions.includes('platform.settings.manage')) throw new ApiError(403, 'permission_denied');
    return { admin: true, base: '/platform/models', token: await sessionToken() };
  }
  const admin = user.permissions.includes('platform.settings.manage') || user.permissions.includes('platform.settings.read');
  if (!admin && !user.permissions.includes('org.configuration.read')) throw new ApiError(403, 'permission_denied');
  return { admin, base: admin ? '/platform/models' : '/models', token: await sessionToken() };
}

export async function modelOptions(): Promise<{ providers: ProviderOption[]; admin: boolean }> {
  const { admin, token } = await access();
  const result = await apiRequest<{ items: { id: string; protocols: string[]; operations: string[]; adapter_available: boolean }[] }>('/providers', { token });
  return { providers: result.items.map((row) => ({ id: row.id, operations: row.operations, adapterAvailable: row.adapter_available })), admin };
}

export async function listModels(query: ModelQuery, cursor?: string): Promise<ApiResult<DirectoryPage<ModelDefinition>>> {
  try {
    const { token, base } = await access();
    return { value: await apiRequest<DirectoryPage<ModelDefinition>>(base + '?' + queryString({ ...query, cursor, include_total: true }), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}

export async function readModel(id: string): Promise<ApiResult<ModelDefinition>> {
  try {
    const { token, base } = await access();
    return { value: await apiRequest<ModelDefinition>(base + '/' + resourceId(id), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}

export async function saveModel(draft: ModelDraft, id?: string, expectedVersion?: number): Promise<ApiResult<ModelDefinition>> {
  try {
    const { token, base } = await access(true);
    const optional = (value: string) => value.trim() || null;
    const body = {
      display_name: draft.display_name.trim(),
      description: optional(draft.description),
      publisher: optional(draft.publisher),
      model_family: optional(draft.model_family),
      model_version: optional(draft.model_version),
      categories: draft.categories,
      operations: draft.operations,
      adapter_status: draft.adapter_status,
      ...(id
        ? { expected_version: expectedVersion, lifecycle: draft.lifecycle }
        : { provider: draft.provider, model_key: draft.model_key.trim() }),
    };
    const value = await apiRequest<ModelDefinition>(base + (id ? '/' + resourceId(id) : ''), { token, method: id ? 'PATCH' : 'POST', body });
    revalidatePath('/models');
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}

export async function retireModel(id: string): Promise<ApiResult<ModelDefinition>> {
  try {
    const { token, base } = await access(true);
    const value = await apiRequest<ModelDefinition>(base + '/' + resourceId(id), { token, method: 'DELETE' });
    revalidatePath('/models');
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}

export async function restoreModel(id: string, expectedVersion: number): Promise<ApiResult<ModelDefinition>> {
  try {
    const { token, base } = await access(true);
    const value = await apiRequest<ModelDefinition>(base + '/' + resourceId(id) + '/restore', { token, method: 'POST', body: { expected_version: expectedVersion } });
    revalidatePath('/models');
    return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
