import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { Dashboard } from '../src/components/dashboards';
import { loadHome } from '../src/lib/home-api';
import { ApiError } from '../src/lib/api';
import type { SessionUser } from '../src/lib/session-user';
import { ROLE_PERMISSIONS } from '../src/lib/roles';

vi.mock('../src/lib/session', () => ({ sessionToken: async () => 'web_private-session' }));
const platform: SessionUser = { id: 'u', name: 'Reviewer', email: 'u@example.com', role: 'platform_admin', contextId: 'platform', permissions: ['platform.health.read'] };
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  vi.stubEnv('PMS_API_BASE_URL', 'http://127.0.0.1:8000/api/v1');
});
const reply = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
it('binds platform figures and audit to authenticated API responses', async () => {
  vi.mocked(fetch).mockImplementation(async input => {
    const path = String(input);
    if (path.includes('dashboard-stats')) return reply({ total_devices: 17, live_devices: 12, total_tenants: 2, inactive_tenants: 1, awaiting_enrollment: 0, offline_after_seconds: 180 });
    if (path.includes('devices-by-tenant')) return reply({ items: [{ label: 'Actual tenant', value: '17' }] });
    return reply({ items: [{ id: 'event', event_type: 'organization.created', occurred_at: '2026-09-23T12:00:00Z' }] });
  });
  const data = await loadHome(platform);
  render(<Dashboard user={platform} data={data} />);
  expect(screen.getAllByText('17').length).toBeGreaterThan(0);
  expect(screen.getByText('Inactive tenants')).toBeInTheDocument();
  expect(screen.getByText('organization created')).toBeInTheDocument();
  expect(screen.queryByText('Expired licences')).not.toBeInTheDocument();
  expect(document.body.textContent).not.toContain('web_private-session');
  for (const [, options] of vi.mocked(fetch).mock.calls) {
    expect(options).toMatchObject({ cache: 'no-store', headers: { Authorization: 'Bearer web_private-session' } });
  }
});
it('loads only personal sessions in the selected tenant and preserves unscored values', async () => {
  vi.mocked(fetch).mockImplementation(async input => String(input).endsWith('/stats')
    ? reply({ sessions: 0, hours_practiced: 0, average_score: null, awaiting_review: 0 })
    : reply({ items: [] }));
  const user = { ...platform, role: 'org_user' as const, contextId: 'org-b', tenant: { name: 'Tenant B', code: 'B' }, permissions: ['org.results.read'] };
  render(<Dashboard user={user} data={await loadHome(user)} />);
  expect(screen.getByText('Not scored')).toBeInTheDocument();
  expect(screen.getByText('No sessions in this scope yet.')).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/organizations/org-b/training/sessions?mine=true'), expect.anything());
  expect(vi.mocked(fetch).mock.calls.every(([url]) => !String(url).includes('/platform/'))).toBe(true);
});
it('does not convert an API failure into invented statistics', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ error: { code: 'organization_inactive' } }), { status: 409 }));
  await expect(loadHome(platform)).rejects.toBeInstanceOf(ApiError);
});
it('shows the two clinical destinations for a tenant administrator', () => {
  const user: SessionUser = { ...platform, role: 'org_admin', contextId: 'tenant-a',
    tenant: { name: 'Tenant A', code: 'A' }, permissions: ROLE_PERMISSIONS.org_admin };
  render(<Dashboard user={user} data={{ cards: [], activity: [] }} />);
  const cards = screen.getByRole('region', { name: 'Clinical content' });
  expect(within(cards).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual([
    '/scenarios',
  ]);
  expect(screen.queryByText('Subscription plan')).not.toBeInTheDocument();
  expect(screen.queryByText('Recent sessions')).not.toBeInTheDocument();
});
