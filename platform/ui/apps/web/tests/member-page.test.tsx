import { describe, expect, it, vi } from 'vitest';
import { DEMO_USERS } from './fixtures/accounts';

const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(), redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`); }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('next/navigation', () => ({ redirect }));
vi.mock('../src/components/PeopleDirectory', () => ({ PeopleDirectory: () => null }));

import Page from '../src/app/(console)/members/page';
import Layout from '../src/app/(console)/members/layout';
import Details from '../src/app/(console)/members/[memberId]/page';

const pages = [
  () => Page(),
  () => Layout({ children: null }),
  () => Details({ params: Promise.resolve({ memberId: 'sample' }) })
];

describe('member route', () => {
  it.each(pages)('redirects visitors before rendering member data', async (page) => {
    currentUser.mockResolvedValue(undefined);
    await expect(page()).rejects.toThrow('redirect:/login');
  });

  it.each(pages)('redirects tenant roles without member management permissions away', async (page) => {
    // Platform admin and org_admin normally have access; org_user does not.
    for (const user of DEMO_USERS.filter((row) => row.role === 'org_user')) {
      currentUser.mockResolvedValue(user);
      await expect(page()).rejects.toThrow('redirect:/home');
    }
  });

  it.each(pages)('denies sessions without the member-manage grant', async (page) => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], permissions: [] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });

  it.each(pages)('does not allow platform access to tenant memberships', async page => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], contextId: 'platform', permissions: ['platform.organizations.read', 'platform.organizations.manage'] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });
  it('binds list and detail routes to the current tenant', async () => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], contextId: 'tenant', permissions: ['org.members.manage'] });
    const page = await Page();
    expect(page.props.user.contextId).toBe('tenant');
    const details = await Details({ params: Promise.resolve({ memberId: 'sample' }) });
    expect(details.props.memberId).toBe('sample');
  });
});
