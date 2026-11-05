import { PermissionProvider, ToastProvider } from '@pms/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DeviceAssociation } from '../src/components/DeviceAssociation';
import { FleetDeviceEditor } from '../src/components/FleetDeviceEditor';
import { DeviceDirectoryProvider } from '../src/components/DeviceDirectoryProvider';
import { listDevices, transferDevice } from '../src/lib/device-actions';
import { validateDeviceDraft, deviceDraft } from '../src/lib/device-editor';
import { DEMO_DEVICES } from '../src/data/devices';
vi.mock('../src/lib/device-actions', () => ({ listDevices: vi.fn(), transferDevice: vi.fn(), saveDevice: vi.fn(), changeDeviceLifecycle: vi.fn() }));
const row = { ...DEMO_DEVICES[0]!, management_etag: 'a'.repeat(64) };
const target = '12345678-1234-4234-8234-123456789012';
beforeEach(() => {
  vi.mocked(listDevices).mockResolvedValue({ value: { items: [], total: 0, has_more: false, next_cursor: null } });
  vi.mocked(transferDevice).mockReset();
});
it('keeps device registration independent of model configuration', async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  render(<FleetDeviceEditor device={null} tenants={{ [target]: 'Destination' }} languages={{ en: 'English' }} onClose={vi.fn()} onSave={save} />);
  expect(screen.queryByLabelText('Processing mode')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Published processing profile')).not.toBeInTheDocument();
  await user.type(screen.getByLabelText('Device name'), 'New device');
  await user.type(screen.getByLabelText('Device unique ID'), 'NEW-DEVICE-001');
  await user.selectOptions(screen.getByLabelText('Tenant association'), target);
  await user.click(screen.getByRole('button', { name: 'Register device' }));
  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ organization_id: target, name: 'New device' })));
});
function show(platform = true) {
  return render(<PermissionProvider permissions={platform ? ['platform.organizations.manage'] : ['org.devices.manage']}><ToastProvider>
    <DeviceDirectoryProvider contextId={platform ? 'platform' : row.organization_id} departments={{}} platform={platform} associationTargets={{ [target]: 'Destination' }}>
      <DeviceAssociation device={row} />
    </DeviceDirectoryProvider>
  </ToastProvider></PermissionProvider>);
}
it('requires explicit transfer confirmation and retains the dialog after refusal', async () => {
  vi.mocked(transferDevice).mockResolvedValue({ error: 'No free device seat.' });
  const user = userEvent.setup(); show();
  await user.click(screen.getByRole('button', { name: 'Transfer to another tenant' }));
  await user.selectOptions(screen.getByLabelText('Destination tenant'), target);
  await user.click(screen.getByRole('button', { name: 'Review transfer' }));
  expect(transferDevice).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Transfer registration' }));
  expect(await screen.findByText('No free device seat.')).toBeInTheDocument();
  expect(screen.getByRole('dialog', { name: 'Confirm tenant transfer' })).toBeInTheDocument();
  expect(transferDevice).toHaveBeenCalledWith('platform', row.id, target, row.name, false, row.management_etag);
});
it('does not offer tenant transfers to a tenant administrator', async () => {
  show(false); await waitFor(() => expect(listDevices).toHaveBeenCalled());
  expect(screen.queryByRole('button', { name: 'Transfer to another tenant' })).not.toBeInTheDocument();
});
it('keeps platform registration limited to public fields and an explicit tenant', async () => {
  const save = vi.fn().mockResolvedValue('No free device seat.');
  const user = userEvent.setup();
  render(<FleetDeviceEditor device={null} tenants={{ [target]: 'Destination' }} languages={{ en: 'English' }} onClose={vi.fn()} onSave={save} />);
  expect(screen.queryByLabelText('Contact name')).not.toBeInTheDocument();
  await user.type(screen.getByLabelText('Device name'), 'New device');
  await user.type(screen.getByLabelText('Device unique ID'), 'NEW-DEVICE-002');
  await user.selectOptions(screen.getByLabelText('Tenant association'), target);
  await user.click(screen.getByRole('button', { name: 'Register device' }));
  expect(await screen.findByText('No free device seat.')).toBeInTheDocument();
  expect(screen.getByLabelText('Device name')).toHaveValue('New device');
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ organization_id: target, name: 'New device' }));
});
it('allows deactivation with old unavailable assignments but validates reactivation', () => {
  const original = { ...row, is_active: true, department_id: target };
  expect(validateDeviceDraft({ ...deviceDraft(original), is_active: false }, {}, false, original)).toEqual({});
  expect(validateDeviceDraft({ ...deviceDraft(original), is_active: true }, {}, false, { ...original, is_active: false })).toMatchObject({ department_id: expect.any(String) });
});
