import { beforeEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/lib/api';
import { currentUser, sessionToken } from '../src/lib/session';
import { listSubscriptions, readSubscription, saveSubscription, saveSubscriptionPlan, subscriptionHistory } from '../src/lib/subscription-actions';
import { DEFAULT_SUBSCRIPTION_QUERY } from '../src/lib/subscriptions';
import { plan, subscription } from './fixtures/subscriptions';
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), apiRequest: vi.fn() }));
const id = subscription.organization_id;
const platform = { id: 'actor', name: 'Admin', email: 'a@example.com', role: 'platform_admin' as const, contextId: 'platform', permissions: ['platform.organizations.read', 'platform.organizations.manage', 'platform.settings.manage'] };
beforeEach(() => { vi.mocked(currentUser).mockResolvedValue(platform); vi.mocked(sessionToken).mockResolvedValue('web_private'); vi.mocked(apiRequest).mockReset(); });
it('uses central scope and the subscription version for manual changes', async () => {
  vi.mocked(apiRequest).mockResolvedValue(subscription);
  await saveSubscription('platform', id, 3, { subscription_status: 'suspended' });
  expect(apiRequest).toHaveBeenCalledWith('/platform/organizations/' + id + '/subscription', expect.objectContaining({ method: 'PATCH', body: { expected_version: 3, subscription_status: 'suspended' } }));
});
it('rejects missing versions and a changed context before contacting the API', async () => {
  expect((await saveSubscription('platform', id, 0, {})).error).toMatch(/Refresh/);
  expect((await readSubscription(id, id)).error).toMatch(/tenant changed/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('limits tenant administrators to their own read and history routes', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...platform, role: 'org_admin', contextId: id, permissions: ['org.settings.read'] });
  vi.mocked(apiRequest).mockResolvedValue(subscription);
  await readSubscription(id, id); expect(apiRequest).toHaveBeenLastCalledWith('/organizations/' + id + '/subscription', expect.anything());
  await subscriptionHistory(id, id); expect(apiRequest).toHaveBeenLastCalledWith(expect.stringContaining('/organizations/' + id + '/subscription/history?'), expect.anything());
  vi.mocked(apiRequest).mockClear();
  expect((await saveSubscription(id, id, 3, {})).error).toMatch(/permission/);
  expect((await readSubscription(id, plan.id)).error).toMatch(/permission/);
  expect((await listSubscriptions(id, DEFAULT_SUBSCRIPTION_QUERY)).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('requires catalog permission separately and keeps prices as exact strings', async () => {
  vi.mocked(apiRequest).mockResolvedValue(plan); await saveSubscriptionPlan('platform', plan);
  expect(apiRequest).toHaveBeenCalledWith('/platform/subscription-plans/' + plan.id, expect.objectContaining({ body: expect.objectContaining({ price_amount: '350000.00', expected_version: 1 }) }));
  vi.mocked(currentUser).mockResolvedValue({ ...platform, permissions: ['platform.organizations.manage'] });
  vi.mocked(apiRequest).mockClear(); expect((await saveSubscriptionPlan('platform', plan)).error).toMatch(/permission/); expect(apiRequest).not.toHaveBeenCalled();
});
