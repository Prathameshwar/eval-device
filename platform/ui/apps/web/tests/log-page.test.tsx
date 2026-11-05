import { describe, expect, it, vi } from 'vitest';
import { logUser } from './fixtures/logs';
const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(), redirect: vi.fn((path: string) => { throw new Error('redirect:' + path); }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('@/lib/log-actions', () => ({ listLogs: vi.fn(), readLog: vi.fn() }));
vi.mock('next/navigation', () => ({ redirect }));
import Page from '../src/app/(console)/logs/page';
import Layout from '../src/app/(console)/logs/layout';
import Details from '../src/app/(console)/logs/[logId]/page';
const pages = [() => Page(), () => Layout({ children: null }), () => Details({ params: Promise.resolve({ logId: 'sample' }) })];
describe('log routes', () => {
  it.each(pages)('redirects anonymous visitors', async page => {
    currentUser.mockResolvedValue(undefined); await expect(page()).rejects.toThrow('redirect:/login');
  });
  it.each(pages)('rejects unrelated platform permissions', async page => {
    currentUser.mockResolvedValue({ ...logUser, contextId: 'platform', role: 'platform_admin', permissions: ['platform.organizations.read'] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });
  it('binds the provider and detail component to the selected context', async () => {
    currentUser.mockResolvedValue(logUser);
    const layout = await Layout({ children: null }); expect(layout.props.user).toEqual(logUser); expect(layout.key).toBe(logUser.contextId);
    const detail = await Details({ params: Promise.resolve({ logId: 'sample' }) });
    expect(detail.props).toMatchObject({ logId: 'sample', user: logUser });
  });
});
