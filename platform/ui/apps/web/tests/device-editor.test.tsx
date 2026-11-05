import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DeviceEditor } from '../src/components/DeviceEditor';
import { FleetDeviceEditor } from '../src/components/FleetDeviceEditor';
import { DEMO_DEVICES, DEMO_DEPARTMENTS } from '../src/data/devices';
import { saveDeviceDraft, deviceDraft, validateDeviceDraft } from '../src/lib/device-editor';

const device = DEMO_DEVICES[0]!;
const valid = () => ({
  ...deviceDraft(null),
  name: 'New SimStation',
  device_unique_id: 'SIM-01',
  device_type: 'manikin' as const
});

describe('device editor data', () => {
  it('requires the new identifier and preserves it during an edit', () => {
    expect(validateDeviceDraft({ ...valid(), device_unique_id: '   ' }, {}, true)).toHaveProperty('device_unique_id');
    expect(saveDeviceDraft({ ...deviceDraft(device), device_unique_id: 'attempted-change' }, device, 'ignored', 'later').device_unique_id).toBe(device.device_unique_id);
  });
  it('requires a nonblank name and an available device type on creation', () => {
    expect(validateDeviceDraft({ ...valid(), name: '   ', device_type: 'unknown' as any }, DEMO_DEPARTMENTS, true))
      .toEqual({ name: 'Enter a device name.', device_type: 'Choose an available device type.' });
  });

  it.each([['device_unique_id', 50], ['name', 256], ['description', 4000], ['location', 512]] as const)(
    'honors the API length boundary for %s', (field, max) => {
      expect(validateDeviceDraft({ ...valid(), [field]: 'x'.repeat(max) }, DEMO_DEPARTMENTS, true)[field]).toBeUndefined();
      expect(validateDeviceDraft({ ...valid(), [field]: 'x'.repeat(max + 1) }, DEMO_DEPARTMENTS, true)[field]).toBeDefined();
    },
  );

  it('validates department when supplied', () => {
    expect(validateDeviceDraft(valid(), DEMO_DEPARTMENTS, true)).toEqual({});
    expect(validateDeviceDraft({ ...valid(), department_id: 'wrong-dept-id' }, DEMO_DEPARTMENTS, true)).toHaveProperty('department_id');
  });

  it('creates inactive records, trims optional fields and keeps identity consistent', () => {
    const saved = saveDeviceDraft({
      ...valid(),
      name: '  New SimStation  ',
      location: '  Floor 3, Lab Z  ',
      is_active: false,
    }, null, 'new-device-id', 'timestamp');
    
    expect(saved).toMatchObject({
      id: 'new-device-id',
      name: 'New SimStation',
      is_active: false,
      device_type: 'manikin',
      location: 'Floor 3, Lab Z',
      created_at: 'timestamp',
      management_version: 1,
    });
  });

  it('preserves IDs and original creation date when editing', () => {
    const draft = { ...deviceDraft(device), name: 'Renamed Device', location: 'Floor 1' };
    expect(validateDeviceDraft(draft, DEMO_DEPARTMENTS, false)).toEqual({});
    expect(saveDeviceDraft(draft, device, 'ignored', 'later')).toMatchObject({
      id: device.id,
      name: 'Renamed Device',
      device_type: device.device_type,
      created_at: device.created_at,
      management_version: (device.management_version ?? 0) + 1,
    });
  });
});

describe('platform device identity controls', () => {
  it('requires a platform-wide unique ID with a 50-character limit at registration', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<FleetDeviceEditor device={null} tenants={{ tenant: 'Tenant' }} languages={{}} onSave={save} onClose={() => {}} />);
    const input = screen.getByLabelText('Device unique ID');
    expect(input).toBeRequired();
    expect(input).toHaveAttribute('maxlength', '50');
    await user.type(screen.getByLabelText('Device name'), 'Manikin');
    await user.selectOptions(screen.getByLabelText('Tenant association'), 'tenant');
    fireEvent.submit(input.closest('form')!);
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByText('Enter a device unique ID of up to 50 characters.')).toBeInTheDocument();
    await user.type(input, 'MANIKIN-001');
    await user.click(screen.getByRole('button', { name: 'Register device' }));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ device_unique_id: 'MANIKIN-001' }));
  });
  it('shows the immutable identifier when editing a registration', async () => {
    render(<FleetDeviceEditor device={device} tenants={{}} languages={{}} onSave={vi.fn()} onClose={() => {}} />);
    const input = screen.getByLabelText('Device unique ID');
    expect(input).toHaveValue(device.device_unique_id);
    expect(input).toHaveAttribute('readonly');
    await userEvent.setup().type(input, 'changed');
    expect(input).toHaveValue(device.device_unique_id);
  });
});

describe('device editor controls', () => {
  it('does not show errors while an untouched form mounts', async () => {
    const user = userEvent.setup();
    render(<StrictMode><DeviceEditor device={null} departments={DEMO_DEPARTMENTS} onSave={vi.fn()} onClose={() => {}} /></StrictMode>);
    expect(screen.getByRole('textbox', { name: 'Device name' })).toHaveFocus();
    await user.tab();
    expect(screen.queryByText('Enter a device name.')).not.toBeInTheDocument();
  });

  it('shows required and type errors, and clears errors as corrected', async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    render(<DeviceEditor device={null} departments={DEMO_DEPARTMENTS} onSave={save} onClose={() => {}} />);
    
    await user.click(screen.getByRole('button', { name: 'Create device' }));
    expect(screen.getByText('Enter a device name.')).toBeInTheDocument();
    
    await user.type(screen.getByRole('textbox', { name: 'Device name' }), 'SimStation B');
    expect(screen.queryByText('Enter a device name.')).not.toBeInTheDocument();
  });

  it('protects a dirty draft on Escape, keeps editing, and discards only after confirmation', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<DeviceEditor device={null} departments={DEMO_DEPARTMENTS} onSave={vi.fn()} onClose={close} />);
    
    await user.type(screen.getByRole('textbox', { name: 'Device name' }), 'Draft Dev');
    await user.keyboard('{Escape}');
    
    const confirmation = screen.getByRole('dialog', { name: 'Discard unsaved changes?' });
    expect(within(confirmation).getByRole('button', { name: 'Keep editing' })).toHaveFocus();
    
    await user.click(within(confirmation).getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByRole('textbox', { name: 'Device name' })).toHaveValue('Draft Dev');
    
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it('does not warn or save an unchanged edit, and allows Cancel immediately', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    const save = vi.fn();
    render(<DeviceEditor device={device} departments={DEMO_DEPARTMENTS} onSave={save} onClose={close} />);
    
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    fireEvent.submit(screen.getByRole('textbox', { name: 'Device name' }).closest('form')!);
    expect(save).not.toHaveBeenCalled();
    
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(close).toHaveBeenCalledOnce();
  });
});
