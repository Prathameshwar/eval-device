import { describe, expect, it, vi } from 'vitest';
import { DEMO_USERS } from './fixtures/accounts';

const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(), redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`); }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('@/lib/device-actions', () => ({
  deviceOptions: async () => ({ departments: {}, profiles: {}, platform: true, contextId: 'platform' }),
  readDevice: async (_context: string, id: string) => ({ value: { id } }),
}));
vi.mock('next/navigation', () => ({ redirect }));

import Page from '../src/app/(console)/devices/page';
import Layout from '../src/app/(console)/devices/layout';
import Details from '../src/app/(console)/devices/[deviceId]/page';

const pages = [
  () => Page({ searchParams: Promise.resolve({}) }),
  () => Layout({ children: null }),
  () => Details({ params: Promise.resolve({ deviceId: 'sample' }) })
];

describe('device route', () => {
  it.each(pages)('redirects visitors before rendering device data', async (page) => {
    currentUser.mockResolvedValue(undefined);
    await expect(page()).rejects.toThrow('redirect:/login');
  });

  it.each(pages)('denies sessions without the device-read grant', async (page) => {
    // Both tenant admins/users and platform admins normally have access based on roles/permissions.
    // A session with empty permissions should be denied and redirected to /home.
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], permissions: [] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });

  it('renders API-loaded device routes', async () => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], contextId: 'platform' }); // platform admin has access
    const layout = await Layout({ children: null });
    expect(layout.props.platform).toBe(true);
    
    const details = await Details({ params: Promise.resolve({ deviceId: 'sample' }) });
    expect(details.props.deviceId).toBe('sample');
  });
});
