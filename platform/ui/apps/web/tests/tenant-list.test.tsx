import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { TenantDirectoryProvider, useTenantDirectory } from '../src/components/TenantDirectoryProvider';
import { TenantList } from '../src/components/TenantList';
import { listTenants } from '../src/lib/tenant-actions';
import { DEMO_TENANTS, TENANT_PLANS } from '../src/data/tenants';
vi.mock('../src/lib/tenant-actions', () => ({ listTenants: vi.fn(), saveTenant: vi.fn(), tenantLifecycle: vi.fn() }));
vi.mock('../src/components/TenantAssociations', () => ({ TenantAssociations: ({ tenant, onClose }: { tenant: { name: string }; onClose: () => void }) => <div role="dialog" aria-label="Association test"><p>{tenant.name}</p><button onClick={onClose}>Close associations</button></div> }));
beforeEach(() => { vi.mocked(listTenants).mockReset(); });
function show() { return render(<PermissionProvider permissions={['platform.organizations.read', 'platform.organizations.manage']}><ToastProvider><TenantDirectoryProvider plans={TENANT_PLANS}><TenantList /></TenantDirectoryProvider></ToastProvider></PermissionProvider>); }
it('shows server records and fetches filtered results instead of filtering a local fixture', async () => {
  vi.mocked(listTenants).mockImplementation(async query => ({ value: { items: query.q ? [] : [DEMO_TENANTS[0]!], total: query.q ? 0 : 1, has_more: false, next_cursor: null } }));
  show();
  expect(await screen.findByText(DEMO_TENANTS[0]!.name)).toBeInTheDocument();
  await userEvent.setup().type(screen.getByRole('searchbox', { name: 'Search tenants' }), 'Missing');
  await waitFor(() => expect(listTenants).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'Missing' }), undefined));
  expect(await screen.findByText('No matching tenants')).toBeInTheDocument();
});
it('shows API failure with retry without claiming the directory is empty', async () => {
  vi.mocked(listTenants).mockResolvedValue({ error: 'Service unavailable' });
  show();
  expect(await screen.findByText('Service unavailable')).toBeInTheDocument();
  expect(screen.queryByText('No tenants yet')).not.toBeInTheDocument();
});
it('uses next cursors and preserves server totals', async () => {
  vi.mocked(listTenants).mockImplementation(async (_, cursor) => ({ value: { items: [DEMO_TENANTS[cursor ? 1 : 0]!], total: 51, has_more: !cursor, next_cursor: cursor ? null : 'signed-cursor' } }));
  show();
  await screen.findByText(DEMO_TENANTS[0]!.name);
  const next = screen.getByRole('button', { name: /next/i });
  await userEvent.setup().click(next);
  await screen.findByText(DEMO_TENANTS[1]!.name);
  expect(listTenants).toHaveBeenLastCalledWith(expect.anything(), 'signed-cursor');
  expect(screen.getByText('51 tenants')).toBeInTheDocument();
});

it('places tenant administration after View and opens the shared popup for exactly that row', async () => {
  const tenant = DEMO_TENANTS[0]!;
  vi.mocked(listTenants).mockResolvedValue({ value: { items: [tenant], total: 1, has_more: false, next_cursor: null } });
  render(<PermissionProvider permissions={['platform.organizations.read', 'platform.users.read']}><ToastProvider><TenantDirectoryProvider plans={TENANT_PLANS}><TenantList /></TenantDirectoryProvider></ToastProvider></PermissionProvider>);
  const button = await screen.findByRole('button', { name: 'Administration for ' + tenant.name });
  const view = screen.getByRole('link', { name: 'View ' + tenant.name });
  expect(view.nextElementSibling).toBe(button);
  await userEvent.setup().click(button);
  expect(screen.getByRole('dialog')).toHaveTextContent(tenant.name);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Close associations' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
it('passes refreshed tenant state to an open administration popup', async () => {
  const tenant = DEMO_TENANTS[0]!;
  vi.mocked(listTenants).mockResolvedValue({ value: { items: [tenant], total: 1, has_more: false, next_cursor: null } });
  function UpdateTenant() {
    const { remember } = useTenantDirectory();
    return <button onClick={() => remember({ ...tenant, name: 'Updated tenant', management_version: tenant.management_version + 1 })}>Update tenant record</button>;
  }
  render(<PermissionProvider permissions={['platform.organizations.read', 'platform.users.read']}><ToastProvider><TenantDirectoryProvider plans={TENANT_PLANS}><TenantList /><UpdateTenant /></TenantDirectoryProvider></ToastProvider></PermissionProvider>);
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Administration for ' + tenant.name }));
  expect(screen.getByRole('dialog')).toHaveTextContent(tenant.name);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Update tenant record' }));
  expect(screen.getByRole('dialog')).toHaveTextContent('Updated tenant');
});
it('offers the shared administration summary to tenant readers without association access', async () => {
  const tenant = DEMO_TENANTS[0]!;
  vi.mocked(listTenants).mockResolvedValue({ value: { items: [tenant], total: 1, has_more: false, next_cursor: null } });
  render(<PermissionProvider permissions={['platform.organizations.read']}><ToastProvider><TenantDirectoryProvider plans={TENANT_PLANS}><TenantList /></TenantDirectoryProvider></ToastProvider></PermissionProvider>);
  await userEvent.setup().click(await screen.findByRole('button', { name: 'Administration for ' + tenant.name }));
  expect(screen.getByRole('dialog')).toHaveTextContent(tenant.name);
});
