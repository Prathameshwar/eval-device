import { describe, expect, it, vi } from 'vitest';
import { DEMO_USERS } from './fixtures/accounts';

const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(), redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`); }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('@/lib/model-actions', () => ({
  modelOptions: async () => ({ providers: [{ id: 'openai', operations: ['text.generate'], adapterAvailable: true }], admin: true }),
  readModel: async (id: string) => ({ value: { id } }),
}));
vi.mock('next/navigation', () => ({ redirect }));

import Page from '../src/app/(console)/models/page';
import Layout from '../src/app/(console)/models/layout';
import Details from '../src/app/(console)/models/[modelId]/page';

const pages = [
  () => Page(),
  () => Layout({ children: null }),
  () => Details({ params: Promise.resolve({ modelId: 'sample' }) }),
];

describe('model route', () => {
  it.each(pages)('redirects visitors before rendering model data', async (page) => {
    currentUser.mockResolvedValue(undefined);
    await expect(page()).rejects.toThrow('redirect:/login');
  });

  it.each(pages)('redirects unauthorized roles away from model catalog settings', async (page) => {
    // Platform admin and org_admin can access settings destinations, but org_user is excluded
    for (const user of DEMO_USERS.filter((row) => row.role === 'org_user')) {
      currentUser.mockResolvedValue(user);
      await expect(page()).rejects.toThrow('redirect:/home');
    }
  });

  it.each(pages)('denies sessions without the settings-read grant', async (page) => {
    currentUser.mockResolvedValue({ ...DEMO_USERS[0], permissions: [] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });

  it('renders children without a second catalog request', async () => {
    currentUser.mockResolvedValue(DEMO_USERS[0]);
    expect(await Layout({ children: 'models' })).toBe('models');
    await expect(Details({ params: Promise.resolve({ modelId: 'sample' }) })).rejects.toThrow('redirect:/models');
  });
});
