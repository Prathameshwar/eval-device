import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PersonEditor } from '../src/components/PersonEditor';
import { personState, type Person } from '../src/lib/people';
import { peopleTenants } from '../src/lib/people-actions';
vi.mock('../src/lib/people-actions', () => ({ peopleTenants: vi.fn() }));
beforeEach(() => {
  vi.mocked(peopleTenants).mockReset();
  vi.mocked(peopleTenants).mockResolvedValue({ value: [{ id: 'tenant', name: 'New college', is_active: false, archived_at: null }] });
});
const row: Person = { id: 'person', display_name: 'Person', email: 'person@example.com', role: 'org_user', invitation_status: 'accepted', is_active: true, archived_at: null, status_reason: null, created_at: '', updated_at: '', management_version: 3 };
const departments = [{ id: 'dept', name: 'Training', is_active: true, archived_at: null }];
it('clears department scope for tenant administrators and never offers pre-acceptance', async () => {
  const user = userEvent.setup(); const save = vi.fn();
  render(<PersonEditor platform={false} row={null} departments={departments} manageAdministrators={false} onSave={save} onClose={vi.fn()} />);
  await user.selectOptions(screen.getByLabelText('Department'), 'dept');
  await user.selectOptions(screen.getByLabelText('Member role'), 'org_admin');
  expect(screen.getByLabelText('Department')).toBeDisabled(); expect(screen.getByLabelText('Department')).toHaveValue('');
  expect(screen.queryByLabelText(/invitation state/i)).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Authentication'), 'oidc');
  expect(screen.queryByLabelText('Display name')).not.toBeInTheDocument();
});
it('keeps global member identity read-only and retains edits after a conflict', async () => {
  const user = userEvent.setup(); const save = vi.fn().mockResolvedValue('Refresh this record.');
  render(<PersonEditor platform={false} row={row} departments={departments} manageAdministrators={false} onSave={save} onClose={vi.fn()} />);
  expect(screen.getByLabelText('Display name')).toHaveAttribute('readonly'); expect(screen.getByLabelText('Email address')).toHaveAttribute('readonly');
  await user.selectOptions(screen.getByLabelText('Member role'), 'org_read_only');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('Refresh this record.')).toBeInTheDocument();
  expect(screen.getByLabelText('Member role')).toHaveValue('org_read_only');
});
it('prevents duplicate submits and accidental close while saving', async () => {
  const user = userEvent.setup(); const save = vi.fn(() => new Promise<string | undefined>(() => {}));
  render(<PersonEditor platform={false} row={row} departments={departments} manageAdministrators={false} onSave={save} onClose={vi.fn()} />);
  await user.dblClick(screen.getByRole('button', { name: 'Save changes' }));
  expect(save).toHaveBeenCalledOnce(); expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
});
it('confirms discarding a changed form', async () => {
  const user = userEvent.setup(); const close = vi.fn();
  render(<PersonEditor platform row={{ ...row, auth_method: 'local' }} departments={[]} manageAdministrators onSave={vi.fn()} onClose={close} />);
  await user.type(screen.getByLabelText('Display name'), ' changed'); await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(close).not.toHaveBeenCalled();
  await user.click(within(screen.getByRole('dialog', { name: 'Discard changes?' })).getByRole('button', { name: 'Discard' }));
  expect(close).toHaveBeenCalledOnce();
});
it('derives expired, archived and unavailable account states truthfully', () => {
  expect(personState({ ...row, invitation_status: 'pending', invitation_expires_at: '2020-01-01T00:00:00Z' })).toBe('Expired');
  expect(personState({ ...row, archived_at: '2020-01-01', is_active: false })).toBe('Archived');
  expect(personState({ ...row, user: { id: 'u', email: row.email, display_name: 'Person', auth_method: 'oidc', is_active: false, archived_at: null } })).toBe('Account unavailable');
});
it('offers only the two administrator creation roles and requires a tenant for tenant administrators', async () => {
  const visitor = userEvent.setup(); const save = vi.fn().mockResolvedValue(undefined);
  render(<PersonEditor platform row={null} departments={[]} manageAdministrators manageTenantAdministrators onSave={save} onClose={vi.fn()} />);
  expect(screen.queryByRole('option', { name: 'User (no platform access)' })).not.toBeInTheDocument();
  await visitor.type(screen.getByLabelText('Display name'), 'New administrator');
  await visitor.type(screen.getByLabelText('Email address'), 'new@example.com');
  await visitor.selectOptions(screen.getByLabelText('Administrator role'), 'org_admin');
  await screen.findByRole('option', { name: 'New college (inactive)' });
  await visitor.click(screen.getByRole('button', { name: 'Create user' }));
  expect(save).not.toHaveBeenCalled();
  await visitor.selectOptions(screen.getByLabelText('Tenant'), 'tenant');
  await visitor.click(screen.getByRole('button', { name: 'Create user' }));
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ role: 'org_admin', organization_id: 'tenant' }));
});
it('clears tenant selection when switching to platform administrator', async () => {
  const visitor = userEvent.setup(); const save = vi.fn().mockResolvedValue(undefined);
  render(<PersonEditor platform row={null} departments={[]} manageAdministrators manageTenantAdministrators onSave={save} onClose={vi.fn()} />);
  await visitor.type(screen.getByLabelText('Display name'), 'Platform owner');
  await visitor.type(screen.getByLabelText('Email address'), 'owner@example.com');
  await visitor.selectOptions(screen.getByLabelText('Administrator role'), 'org_admin');
  await screen.findByRole('option', { name: 'New college (inactive)' });
  await visitor.selectOptions(screen.getByLabelText('Tenant'), 'tenant');
  await visitor.selectOptions(screen.getByLabelText('Administrator role'), 'platform_admin');
  expect(screen.queryByLabelText('Tenant')).not.toBeInTheDocument();
  await visitor.click(screen.getByRole('button', { name: 'Create user' }));
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ role: 'platform_admin', organization_id: '' }));
});
it('retains input while tenant loading fails and allows retry without offering archived tenants', async () => {
  const visitor = userEvent.setup();
  vi.mocked(peopleTenants).mockRejectedValueOnce(new Error('network'));
  render(<PersonEditor platform row={null} departments={[]} manageAdministrators={false} manageTenantAdministrators onSave={vi.fn()} onClose={vi.fn()} />);
  expect(screen.queryByRole('option', { name: 'Platform administrator' })).not.toBeInTheDocument();
  await visitor.type(screen.getByLabelText('Display name'), 'New tenant administrator');
  await visitor.selectOptions(screen.getByLabelText('Administrator role'), 'org_admin');
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load tenants.');
  expect(screen.getByRole('button', { name: 'Create user' })).toBeDisabled();
  vi.mocked(peopleTenants).mockResolvedValueOnce({ value: [
    { id: 'archived', name: 'Archived college', is_active: false, archived_at: '2026-09-20' },
    { id: 'live', name: 'Available college', is_active: true, archived_at: null },
  ] });
  await visitor.click(screen.getByRole('button', { name: 'Retry tenants' }));
  await screen.findByRole('option', { name: 'Available college' });
  expect(screen.queryByRole('option', { name: /Archived college/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Display name')).toHaveValue('New tenant administrator');
});
