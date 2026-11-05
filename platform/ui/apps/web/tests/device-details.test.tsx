import { PermissionProvider, ToastProvider } from '@pms/ui';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DeviceDirectoryProvider } from '../src/components/DeviceDirectoryProvider';
import { DeviceDetails } from '../src/components/DeviceDetails';
import { listDevices, readDevice, readDeviceConfiguration, changeDeviceLifecycle, saveDevice, issueEnrollment } from '../src/lib/device-actions';
import type { Device } from '../src/lib/device-directory';
import { DEMO_DEVICES } from '../src/data/devices';
vi.mock('../src/lib/device-actions', () => ({ listDevices: vi.fn(), transferDevice: vi.fn(), readDeviceConfiguration: vi.fn(), saveDevice: vi.fn(), changeDeviceLifecycle: vi.fn(), issueEnrollment: vi.fn(), readDevice: vi.fn() }));
const row = { ...DEMO_DEVICES[0]!, management_etag: 'a'.repeat(64), credential_status: 'active' as const };
beforeEach(() => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [], total: 0, has_more: false, next_cursor: null } });
  vi.mocked(readDeviceConfiguration).mockResolvedValue({ value: { language: 'hi', operational: true, applied: false, modelsAssigned: true } });
  vi.mocked(changeDeviceLifecycle).mockReset();
  vi.mocked(issueEnrollment).mockReset();
  vi.mocked(readDevice).mockResolvedValue({ value: row });
});
function show(platform = false, overrides: Partial<Device> = {}) { return render(<PermissionProvider permissions={platform ? ['platform.health.read', 'platform.organizations.manage'] : ['org.devices.summary.read', 'org.devices.manage', 'org.configuration.read']}><ToastProvider><DeviceDirectoryProvider contextId={platform ? 'platform' : row.organization_id} platform={platform} departments={{}}><DeviceDetails deviceId={row.id} initialDevice={{ ...row, ...overrides, summary_only: platform }} /></DeviceDirectoryProvider></ToastProvider></PermissionProvider>); }
afterEach(() => vi.useRealTimers());
it('loads a deep-linked device and its effective configuration', async () => {
  show();
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(row.name);
  expect(await screen.findByText('Awaiting device acknowledgement')).toBeInTheDocument();
  expect(readDeviceConfiguration).toHaveBeenCalledWith(row.organization_id, row.id);
});
it('retirement is confirmed and only changes the record after API success', async () => {
  show();
  const user = userEvent.setup();
  vi.mocked(changeDeviceLifecycle).mockResolvedValue({ value: { ...row, enrollment_state: 'retired', is_active: false, credential_status: 'revoked' } });
  await user.click(screen.getByRole('button', { name: 'Device actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Retire' }));
  expect(changeDeviceLifecycle).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Retire device' }));
  expect(await screen.findByText('Retired device')).toBeInTheDocument();
  expect(changeDeviceLifecycle).toHaveBeenCalledWith(row.organization_id, row.id, 'retire', row.management_etag);
  expect(screen.queryByRole('button', { name: 'Edit device' })).not.toBeInTheDocument();
});
it('platform summaries cannot request configuration or enrollment', async () => {
  vi.mocked(readDeviceConfiguration).mockClear();
  show(true);
  await waitFor(() => expect(listDevices).toHaveBeenCalled());
  expect(screen.getByRole('button', { name: 'Edit device' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Issue enrollment token' })).not.toBeInTheDocument();
  expect(readDeviceConfiguration).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: 'Assign Department or Profile' })).not.toBeInTheDocument();
});
it('recovers from a refresh transport failure and clears the error after retry', async () => {
  show();
  await screen.findByText('Awaiting device acknowledgement');
  const user = userEvent.setup();
  vi.mocked(readDevice).mockRejectedValueOnce(new Error('connection lost'));
  await user.click(screen.getByRole('button', { name: 'Refresh device status' }));
  expect(await screen.findByText('Unable to refresh device status. Try again.')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Refresh device status' }));
  await waitFor(() => expect(screen.queryByText('Unable to refresh device status. Try again.')).not.toBeInTheDocument());
  expect(screen.getByText('Awaiting device acknowledgement')).toBeInTheDocument();
});

it('platform status edits let the API validate private assignments and allow pending-token revocation', async () => {
  const original = { ...row, is_active: false, department_id: '12345678-1234-4234-8234-123456789012', credential_status: 'revoked' as const };
  vi.mocked(saveDevice).mockResolvedValue({ value: { ...original, is_active: true, summary_only: true } });
  show(true, original);
  const user = userEvent.setup();
  expect(screen.getByRole('button', { name: 'Revoke device access' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Edit device' }));
  await user.selectOptions(screen.getByLabelText('Device status'), 'true');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(saveDevice).toHaveBeenCalledWith('platform', expect.objectContaining({ is_active: true }), row.id, row.management_etag));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit registration' })).not.toBeInTheDocument());
});

const issuedToken = 'enr_fixture_only_for_tests';
const tokenResult = () => ({ enrollment_token: issuedToken, expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString() });
async function issueToken(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Issue enrollment token' }));
  await user.click(screen.getByRole('button', { name: 'Issue token' }));
}

it.each(['laptop', 'manikin'] as const)('lets a tenant admin issue and copy a %s token and explains pending credentials', async deviceType => {
  const user = userEvent.setup();
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
  vi.mocked(issueEnrollment).mockResolvedValue({ value: tokenResult() });
  const device = { ...row, device_type: deviceType, credential_status: 'not_issued' as const, enrollment_state: 'pending' as const };
  vi.mocked(readDevice).mockResolvedValue({ value: device });
  show(false, device);
  expect(screen.getByText(/A device credential is created after/)).toBeInTheDocument();
  await issueToken(user);
  const dialog = await screen.findByRole('dialog', { name: 'Enrollment token ready' });
  expect(screen.queryByRole('dialog', { name: 'Issue an enrollment token?' })).not.toBeInTheDocument();
  expect(within(dialog).getByLabelText('Enrollment token')).toHaveValue(issuedToken);
  expect(within(dialog).getByLabelText('Device ID')).toHaveValue(row.id);
  await user.click(within(dialog).getByRole('button', { name: 'Copy token' }));
  expect(clipboard).toHaveBeenCalledWith(issuedToken);
  expect(await within(dialog).findByText('Enrollment token copied.')).toBeInTheDocument();
  expect(issueEnrollment).toHaveBeenCalledTimes(1);
  expect(issueEnrollment).toHaveBeenCalledWith(row.organization_id, row.id, row.management_etag);
  await user.click(within(dialog).getByRole('button', { name: 'Close and hide token' }));
  expect(screen.queryByLabelText('Enrollment token')).not.toBeInTheDocument();
});

it('preserves a successfully issued token when refreshing device status fails', async () => {
  const user = userEvent.setup();
  vi.mocked(issueEnrollment).mockResolvedValue({ value: tokenResult() });
  show();
  await screen.findByText('Awaiting device acknowledgement');
  vi.mocked(readDevice).mockRejectedValueOnce(new Error('connection lost'));
  await issueToken(user);
  const dialog = await screen.findByRole('dialog', { name: 'Enrollment token ready' });
  expect(await within(dialog).findByText(/The token was issued, but device status/)).toBeInTheDocument();
  expect(within(dialog).getByLabelText('Enrollment token')).toHaveValue(issuedToken);
  expect(issueEnrollment).toHaveBeenCalledTimes(1);
});

it('shows the token immediately while the status refresh is still pending', async () => {
  const user = userEvent.setup();
  vi.mocked(issueEnrollment).mockResolvedValue({ value: tokenResult() });
  show();
  await screen.findByText('Awaiting device acknowledgement');
  let finishRefresh!: (value: Awaited<ReturnType<typeof readDevice>>) => void;
  vi.mocked(readDevice).mockImplementationOnce(() => new Promise(resolve => { finishRefresh = resolve; }));
  await issueToken(user);
  const dialog = screen.getByRole('dialog', { name: 'Enrollment token ready' });
  expect(within(dialog).getByLabelText('Enrollment token')).toHaveValue(issuedToken);
  expect(screen.getByRole('button', { name: 'Issue enrollment token' })).toBeDisabled();
  await user.click(within(dialog).getByRole('button', { name: 'Close and hide token' }));
  await act(async () => { finishRefresh({ value: row }); });
  expect(screen.queryByLabelText('Enrollment token')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Issue enrollment token' })).toBeEnabled();
  expect(issueEnrollment).toHaveBeenCalledTimes(1);
});

it('keeps the token selectable when clipboard access fails', async () => {
  const user = userEvent.setup();
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('not allowed'));
  vi.mocked(issueEnrollment).mockResolvedValue({ value: tokenResult() });
  show();
  await issueToken(user);
  const dialog = await screen.findByRole('dialog', { name: 'Enrollment token ready' });
  await user.click(within(dialog).getByRole('button', { name: 'Copy token' }));
  expect(await within(dialog).findByText(/Clipboard access is unavailable/)).toBeInTheDocument();
  const field = within(dialog).getByLabelText('Enrollment token') as HTMLInputElement;
  expect(field).toHaveFocus();
  expect(field.selectionStart).toBe(0);
  expect(field.selectionEnd).toBe(issuedToken.length);
});

it('keeps an issuance error in the confirmation without pretending a token exists', async () => {
  const user = userEvent.setup();
  vi.mocked(issueEnrollment).mockResolvedValue({ error: 'Issuance unavailable.' });
  show();
  await screen.findByText('Awaiting device acknowledgement');
  await issueToken(user);
  expect(await screen.findByText('Issuance unavailable.')).toBeInTheDocument();
  expect(screen.getByRole('dialog', { name: 'Issue an enrollment token?' })).toBeInTheDocument();
  expect(screen.queryByLabelText('Enrollment token')).not.toBeInTheDocument();
});

it('does not let a delayed configuration response erase an enrollment error', async () => {
  const user = userEvent.setup();
  let finishConfiguration!: (value: Awaited<ReturnType<typeof readDeviceConfiguration>>) => void;
  vi.mocked(readDeviceConfiguration).mockImplementationOnce(() => new Promise(resolve => { finishConfiguration = resolve; }));
  vi.mocked(issueEnrollment).mockResolvedValue({ error: 'Issuance unavailable.' });
  show();
  await issueToken(user);
  const dialog = screen.getByRole('dialog', { name: 'Issue an enrollment token?' });
  expect(within(dialog).getByText('Issuance unavailable.')).toBeInTheDocument();
  await act(async () => { finishConfiguration({ value: { language: 'en', operational: true, applied: false, modelsAssigned: true } }); });
  expect(within(dialog).getByText('Issuance unavailable.')).toBeInTheDocument();
});

it('hides a token if tenant management permission is removed', async () => {
  const user = userEvent.setup();
  vi.mocked(issueEnrollment).mockResolvedValue({ value: tokenResult() });
  const view = show();
  await issueToken(user);
  await screen.findByRole('dialog', { name: 'Enrollment token ready' });
  view.rerender(<PermissionProvider permissions={['org.devices.summary.read']}><ToastProvider><DeviceDirectoryProvider contextId={row.organization_id} departments={{}}><DeviceDetails deviceId={row.id} initialDevice={row} /></DeviceDirectoryProvider></ToastProvider></PermissionProvider>);
  expect(screen.queryByLabelText('Enrollment token')).not.toBeInTheDocument();
});

it('automatically hides the one-time token at expiry', async () => {
  vi.useFakeTimers();
  vi.mocked(issueEnrollment).mockResolvedValue({ value: { enrollment_token: issuedToken, expires_at: new Date(Date.now() + 1000).toISOString() } });
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Issue enrollment token' }));
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Issue token' })); });
  expect(screen.getByRole('dialog', { name: 'Enrollment token ready' })).toBeInTheDocument();
  await act(async () => { vi.advanceTimersByTime(1001); });
  expect(screen.queryByLabelText('Enrollment token')).not.toBeInTheDocument();
});
