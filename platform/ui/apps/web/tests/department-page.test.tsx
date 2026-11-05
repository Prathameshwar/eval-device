import { describe, expect, it, vi } from 'vitest';
import { DEMO_USERS } from './fixtures/accounts';

const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('next/navigation', () => ({ redirect }));

import Page from '../src/app/(console)/departments/page';
import Layout from '../src/app/(console)/departments/layout';
import Details from '../src/app/(console)/departments/[departmentId]/page';

const pages = [
  () => Page(),
  () => Layout({ children: null }),
  () => Details({ params: Promise.resolve({ departmentId: 'sample' }) }),
];

describe('department route', () => {
  it.each(pages)('redirects visitors before rendering department data', async (page) => {
    currentUser.mockResolvedValue(undefined);
    await expect(page()).rejects.toThrow('redirect:/login');
  });

  it.each(pages)('redirects tenant roles without department management permissions away', async (page) => {
    // Platform admin and org_admin normally have access; org_user does not.
    for (const user of DEMO_USERS.filter((row) => row.role === 'org_user')) {
      currentUser.mockResolvedValue(user);
      await expect(page()).rejects.toThrow('redirect:/home');
    }
  });

  it.each(pages)('denies sessions without the department-manage grant', async (page) => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], permissions: [] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });

  it('binds real department pages to the selected tenant', async () => {
    currentUser.mockResolvedValue({
      ...DEMO_USERS.find((u) => u.role === 'org_admin'),
      contextId: 'tenant-context',
    });
    const list = await Page();
    expect(list.props.contextId).toBe('tenant-context');
    const details = await Details({
      params: Promise.resolve({ departmentId: 'sample' }),
    });
    expect(details.props.id).toBe('sample');
    expect(details.props.contextId).toBe('tenant-context');
  });
  it('does not give platform administrators implicit department access', async () => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], contextId: 'platform' });
    await expect(Page()).rejects.toThrow('redirect:/home');
  });
});
