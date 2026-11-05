'use server';
import { revalidatePath } from 'next/cache';
import { ApiError, apiRequest } from './api';
import { currentUser, sessionToken } from './session';
import { queryString, resourceId } from './console-api';
import { consoleError } from './console-errors';
import type { ApiResult, DirectoryPage } from './directory-api';
import type { Plan, Subscription, SubscriptionDraft, SubscriptionEvent, SubscriptionQuery } from './subscriptions';

async function access(contextId: string, permission?: string) {
  const user = await currentUser();
  if (!user) throw new ApiError(401, 'authentication_required');
  if (user.contextId !== contextId) throw new ApiError(409, 'context_changed');
  const platform = contextId === 'platform';
  if (permission && !platform || !user.permissions.includes(permission ?? (platform ? 'platform.organizations.read' : 'org.settings.read'))) throw new ApiError(403, 'permission_denied');
  return { user, platform, token: await sessionToken() };
}
function version(value: number) {
  if (!Number.isSafeInteger(value) || value < 1) throw new ApiError(422, 'version_required');
  return value;
}
function path(contextId: string, organizationId: string) {
  if (contextId !== 'platform' && contextId !== organizationId) throw new ApiError(403, 'permission_denied');
  return (contextId === 'platform' ? '/platform' : '') + '/organizations/' + resourceId(organizationId) + '/subscription';
}
function changed() { for (const route of ['/licenses', '/tenants', '/home']) revalidatePath(route); }
export async function subscriptionPlans(contextId: string): Promise<ApiResult<Plan[]>> {
  try {
    const { platform, token } = await access(contextId, contextId === 'platform' ? 'platform.settings.read' : undefined);
    return { value: (await apiRequest<{ items: Plan[] }>(platform ? '/platform/subscription-plans' : '/subscription-plans', { token })).items };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function listSubscriptions(contextId: string, query: SubscriptionQuery, cursor?: string): Promise<ApiResult<DirectoryPage<Subscription>>> {
  try {
    const { token } = await access(contextId, 'platform.organizations.read');
    return { value: await apiRequest<DirectoryPage<Subscription>>('/platform/subscriptions?' + queryString({ ...query, cursor }), { token }) };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function readSubscription(contextId: string, organizationId: string): Promise<ApiResult<Subscription>> {
  try { const { token } = await access(contextId); return { value: await apiRequest<Subscription>(path(contextId, organizationId), { token }) }; }
  catch (error) { return { error: consoleError(error) }; }
}
export async function subscriptionHistory(contextId: string, organizationId: string, cursor?: string): Promise<ApiResult<DirectoryPage<SubscriptionEvent>>> {
  try { const { token } = await access(contextId); return { value: await apiRequest<DirectoryPage<SubscriptionEvent>>(path(contextId, organizationId) + '/history?' + queryString({ limit: 25, cursor }), { token }) }; }
  catch (error) { return { error: consoleError(error) }; }
}
export async function saveSubscription(contextId: string, organizationId: string, expectedVersion: number, draft: Partial<SubscriptionDraft>): Promise<ApiResult<Subscription>> {
  try {
    const { token } = await access(contextId, 'platform.organizations.manage');
    const value = await apiRequest<Subscription>(path(contextId, organizationId), { token, method: 'PATCH', body: { ...draft, expected_version: version(expectedVersion) } });
    changed(); return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
export async function saveSubscriptionPlan(contextId: string, plan: Plan): Promise<ApiResult<Plan>> {
  try {
    const { token } = await access(contextId, 'platform.settings.manage');
    const value = await apiRequest<Plan>('/platform/subscription-plans/' + resourceId(plan.id), {
      token, method: 'PATCH', body: { expected_version: version(plan.configuration_version),
        name: plan.name.trim(), price_amount: plan.price_amount, currency: plan.currency, billing_period: plan.billing_period,
        max_users: plan.max_users, max_devices: plan.max_devices, is_active: plan.is_active },
    });
    changed(); return { value };
  } catch (error) { return { error: consoleError(error) }; }
}
