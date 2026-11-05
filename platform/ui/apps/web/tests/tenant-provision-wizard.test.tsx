import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { TenantDirectoryProvider } from '../src/components/TenantDirectoryProvider';
import { TenantProvisionWizard } from '../src/components/TenantProvisionWizard';
import { DEMO_TENANTS } from '../src/data/tenants';
import { listDevices } from '../src/lib/device-actions';
import { findAdministrators, listTenants, provisionTenant } from '../src/lib/tenant-actions';

vi.mock('../src/lib/device-actions', () => ({ listDevices: vi.fn() }));
vi.mock('../src/lib/tenant-actions', () => ({
  listTenants: vi.fn(), saveTenant: vi.fn(), tenantLifecycle: vi.fn(),
  findAdministrators: vi.fn(), provisionTenant: vi.fn(),
}));

const id = '12345678-1234-4234-8234-123456789012';
const tenant = DEMO_TENANTS[0]!;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listTenants).mockResolvedValue({ value: { items: [], total: 0, has_more: false, next_cursor: null } });
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [], total: 0, has_more: false, next_cursor: null } });
  vi.mocked(findAdministrators).mockResolvedValue({ value: [] });
  vi.mocked(provisionTenant).mockResolvedValue({ value: { tenant, device: { id }, administrator: { id } } });
});
function show() {
  return render(<TenantDirectoryProvider plans={{ [id]: 'Standard' }}>
    <TenantProvisionWizard />
  </TenantDirectoryProvider>);
}

it('requires each step and provisions an active tenant, manikin, and new administrator', async () => {
  const user = userEvent.setup();
  show();
  expect(screen.getByLabelText('Tenant name')).not.toHaveAttribute('aria-invalid', 'true');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getAllByText(/Enter a tenant name/).length).toBeGreaterThan(0);
  expect(screen.getByLabelText('Tenant name')).toHaveAttribute('aria-invalid', 'true');
  await user.type(screen.getByLabelText('Tenant name'), 'Wizard hospital');
  await user.selectOptions(screen.getByLabelText('Subscription plan'), id);
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByRole('heading', { name: 'Device' })).toBeInTheDocument();
  await user.type(screen.getByLabelText('Device name'), 'Simulation manikin');
  await user.type(screen.getByLabelText('Device unique ID'), 'MANIKIN-001');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.type(screen.getByLabelText('Full name'), 'Hospital admin');
  await user.type(screen.getByLabelText('Email'), 'admin@example.com');
  await user.type(screen.getByLabelText('Password', { exact: true }), 'test-private-password-2026');
  await user.type(screen.getByLabelText('Confirm password'), 'test-private-password-2026');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByText(/Active tenant and device/)).toBeInTheDocument();
  expect(screen.getByText('Fictional starter profile, inactive until tenant review')).toBeInTheDocument();
  expect(screen.getByText('Cardiology, Nephrology, Respiratory Medicine; active')).toBeInTheDocument();
  expect(screen.getByText('Chest discomfort interview, Wheeze interview; inactive until tenant review')).toBeInTheDocument();
  expect(screen.getByText(/Published starters are available to select in the desktop app without activating/)).toBeInTheDocument();
  expect(screen.getByText('Two active system starters in English and Hindi; no tenant clinician approval')).toBeInTheDocument();
  expect(screen.getByText('Chest discomfort in English; each user saves their own selection')).toBeInTheDocument();
  expect(screen.getByText(/Cases include presentation and symptoms, history, and eight vitals/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Finish setup' }));
  await waitFor(() => expect(provisionTenant).toHaveBeenCalledWith(
    expect.objectContaining({ name: 'Wizard hospital', subscription_plan_id: id }),
    { kind: 'new', name: 'Simulation manikin', device_unique_id: 'MANIKIN-001', device_type: 'manikin' },
    { kind: 'new', display_name: 'Hospital admin', email: 'admin@example.com', password: 'test-private-password-2026' },
  ));
  expect(await screen.findByText(/administrator are ready/)).toBeInTheDocument();
  expect(screen.getByText(/Three clinical specialties are active/)).toBeInTheDocument();
  expect(screen.getByText(/Alex patient profile and two editable cases are inactive/)).toBeInTheDocument();
  expect(screen.getByText(/Two published scenarios are available in the desktop app as system starters/)).toBeInTheDocument();
  expect(screen.getByText(/Enroll the device and configure its models before device training/)).toBeInTheDocument();
  expect(screen.queryByDisplayValue('test-private-password-2026')).not.toBeInTheDocument();
});

it('selects a current device and an eligible existing user for atomic transfer', async () => {
  const user = userEvent.setup();
  const device = { id, name: 'Source laptop', organization_id: id, organization_name: 'Old tenant', management_etag: 'a'.repeat(64) };
  const person = { id, display_name: 'Existing admin', email: 'existing@example.com' };
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [device], total: 1, has_more: false, next_cursor: null } } as never);
  vi.mocked(findAdministrators).mockResolvedValue({ value: [person] });
  show();
  await user.type(screen.getByLabelText('Tenant name'), 'Transferred hospital');
  await user.selectOptions(screen.getByLabelText('Subscription plan'), id);
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.selectOptions(screen.getByLabelText('Device choice'), 'existing');
  await user.type(screen.getByLabelText('Find device by name or ID'), 'Source');
  await user.click(screen.getByRole('button', { name: 'Search' }));
  await user.click(await screen.findByRole('radio', { name: /Source laptop/ }));
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.selectOptions(screen.getByLabelText('Administrator choice'), 'existing');
  await user.type(screen.getByLabelText('Find user by name or email'), 'Existing');
  await user.click(screen.getByRole('button', { name: 'Search' }));
  await user.click(await screen.findByRole('radio', { name: /Existing admin/ }));
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.click(screen.getByRole('button', { name: 'Finish setup' }));
  await waitFor(() => expect(provisionTenant).toHaveBeenCalledWith(
    expect.anything(), { kind: 'existing', device_id: id, expected_etag: 'a'.repeat(64) },
    { kind: 'existing', user_id: id },
  ));
});

it('recovers from failed device and user searches and explains empty results', async () => {
  const user = userEvent.setup();
  show();
  await user.type(screen.getByLabelText('Tenant name'), 'Search hospital');
  await user.selectOptions(screen.getByLabelText('Subscription plan'), id);
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.selectOptions(screen.getByLabelText('Device choice'), 'existing');
  await user.type(screen.getByLabelText('Find device by name or ID'), 'missing');
  vi.mocked(listDevices).mockRejectedValueOnce(new Error('network'));
  await user.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText('Unable to search devices. Try again.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Search' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText('No current devices found. Try a different name or ID.')).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Device choice'), 'new');
  await user.type(screen.getByLabelText('Device name'), 'New laptop');
  await user.type(screen.getByLabelText('Device unique ID'), 'LAPTOP-002');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.selectOptions(screen.getByLabelText('Administrator choice'), 'existing');
  await user.type(screen.getByLabelText('Find user by name or email'), 'missing');
  vi.mocked(findAdministrators).mockRejectedValueOnce(new Error('network'));
  await user.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText('Unable to search users. Try again.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Search' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Search' }));
  expect(await screen.findByText('No active, verified users found. Try another name or email.')).toBeInTheDocument();
});
