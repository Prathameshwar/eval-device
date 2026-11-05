import { act, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { MemberCapabilities } from '../src/components/MemberCapabilities';
import * as actions from '../src/lib/capability-actions';
import userEvent from '@testing-library/user-event';

vi.mock('../src/lib/capability-actions', () => ({ listCapabilities: vi.fn(), setCapability: vi.fn() }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(actions.listCapabilities).mockResolvedValue({ value: [] });
});

it('shows clinical author as permanent for a tenant administrator', async () => {
  await act(async () => { render(<MemberCapabilities contextId="tenant" memberId="admin" role="org_admin" departmentId={null} />); });
  const row = screen.getByText('Clinical author').closest('li');
  expect(row).not.toBeNull();
  expect(row).toHaveTextContent('Included with tenant administrator role');
  expect(within(row!).queryByRole('button')).not.toBeInTheDocument();
  expect(actions.listCapabilities).toHaveBeenCalledWith('tenant', 'admin');
});

it('still requires an explicit clinical author assignment for tenant staff', async () => {
  await act(async () => { render(<MemberCapabilities contextId="tenant" memberId="staff" role="org_user" departmentId={null} />); });
  const row = screen.getByText('Clinical author').closest('li');
  expect(row).not.toBeNull();
  expect(within(row!).getByRole('button', { name: 'Assign' })).toBeInTheDocument();
});

it('allows revocation after a role change makes an assignment ineligible', async () => {
  vi.mocked(actions.listCapabilities).mockResolvedValue({ value: [{ capability: 'org.clinical.author',
    granted_at: '2026-10-04', granted_by: 'admin', revoked_at: null, revoked_by: null }] });
  vi.mocked(actions.setCapability).mockResolvedValue({ value: true });
  await act(async () => { render(<MemberCapabilities contextId="tenant" memberId="staff" role="org_trainee" />); });
  const row = screen.getByText('Clinical author').closest('li')!;
  expect(row).toHaveTextContent('Inactive for this role or scope');
  await userEvent.setup().click(within(row).getByRole('button', { name: 'Revoke' }));
  expect(actions.setCapability).toHaveBeenCalledWith('tenant', 'staff', 'org.clinical.author', false);
});

it('prevents changes until assignments load and offers recovery after a load error', async () => {
  vi.mocked(actions.listCapabilities).mockResolvedValue({ error: 'Unavailable' });
  await act(async () => { render(<MemberCapabilities contextId="tenant" memberId="staff" role="org_user" />); });
  expect(screen.getAllByRole('button', { name: 'Assign' }).every(button => button.hasAttribute('disabled'))).toBe(true);
  vi.mocked(actions.listCapabilities).mockResolvedValue({ value: [] });
  await userEvent.setup().click(screen.getByRole('button', { name: 'Reload responsibilities' }));
  expect(within(screen.getByText('Clinical author').closest('li')!).getByRole('button', { name: 'Assign' })).toBeEnabled();
});
