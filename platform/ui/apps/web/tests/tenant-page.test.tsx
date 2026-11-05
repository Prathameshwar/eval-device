import { describe, expect, it, vi } from 'vitest';
import { DEMO_USERS } from './fixtures/accounts';

const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(), redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`); }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('@/lib/tenant-actions', () => ({
  tenantPlans: async () => ({ plans: { real: 'Actual plan' }, activePlans: { real: 'Actual plan' } }),
  readTenant: async (id: string) => ({ value: { id } }),
}));
vi.mock('next/navigation', () => ({ redirect }));
import Page from '../src/app/(console)/tenants/page';
import Layout from '../src/app/(console)/tenants/layout';
import Details from '../src/app/(console)/tenants/[tenantId]/page';
const pages = [() => Page(), () => Layout({ children: null }), () => Details({ params: Promise.resolve({ tenantId: 'sample' }) })];

describe('tenant route', () => {
  it.each(pages)('redirects visitors before rendering tenant data', async (page) => {
    currentUser.mockResolvedValue(undefined);
    await expect(page()).rejects.toThrow('redirect:/login');
  });
  it.each(pages)('redirects tenant roles away from the platform directory and details', async (page) => {
    for (const user of DEMO_USERS.filter((row) => row.role !== 'platform_admin')) {
      currentUser.mockResolvedValue(user);
      await expect(page()).rejects.toThrow('redirect:/home');
    }
  });
  it.each(pages)('denies platform sessions without the tenant-read grant', async (page) => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], permissions: [] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });
  it('renders the list for the platform reader', async () => {
    currentUser.mockResolvedValue(DEMO_USERS[0]);
    const layout = await Layout({ children: null });
    expect(layout.props.plans).toEqual({ real: 'Actual plan' });
    const details = await Details({ params: Promise.resolve({ tenantId: 'sample' }) });
    expect(details.props.tenantId).toBe('sample');
  });
});
