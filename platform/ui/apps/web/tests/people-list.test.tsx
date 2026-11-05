import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PeopleDirectory } from '../src/components/PeopleDirectory';
import * as actions from '../src/lib/people-actions';
import type { Person } from '../src/lib/people';
vi.mock('../src/lib/people-actions', () => ({ listPeople: vi.fn(), peopleDepartments: vi.fn(), peopleTenants: vi.fn(), readPerson: vi.fn(), savePerson: vi.fn(), managePerson: vi.fn() }));
const row: Person = { id: 'member', display_name: 'Person', email: 'person@example.com', role: 'org_user', invitation_status: 'accepted', user_id: 'user', is_active: true, archived_at: null, status_reason: null, created_at: '', updated_at: '', management_version: 5 };
const user = { id: 'owner', name: 'Owner', email: 'owner@example.com', role: 'org_admin' as const, contextId: 'tenant', permissions: ['org.members.manage'] };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [row], total: 1, next_cursor: null, has_more: false } });
  vi.mocked(actions.peopleDepartments).mockResolvedValue({ value: [] });
  vi.mocked(actions.readPerson).mockResolvedValue({ value: row });
});
it('reads a direct detail independently of the list page and permits refresh', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [], total: 0, next_cursor: null, has_more: false } });
  render(<PeopleDirectory user={user} memberId="member" />);
  expect(await screen.findByRole('heading', { name: 'Person' })).toBeInTheDocument();
  expect(actions.readPerson).toHaveBeenCalledWith('tenant', 'member');
  await visitor.click(screen.getByRole('button', { name: 'Refresh' }));
  expect(actions.readPerson).toHaveBeenCalledTimes(2);
});
it('keeps a rejected archive dialog visible and sends its selected version', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.managePerson).mockResolvedValue({ error: 'An active administrator is required.' });
  render(<PeopleDirectory user={user} />);
  await visitor.click(await screen.findByRole('button', { name: 'Actions for Person' }));
  await visitor.click(await screen.findByRole('menuitem', { name: 'Archive' }));
  const dialog = screen.getByRole('dialog', { name: 'Archive for Person?' });
  await visitor.click(within(dialog).getByRole('button', { name: 'Archive' }));
  expect(await within(dialog).findByText('An active administrator is required.')).toBeInTheDocument();
  expect(actions.managePerson).toHaveBeenCalledWith('tenant', 'member', 'archive', 5);
});
it('never offers activation for unaccepted invitations', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [{ ...row, user_id: null, is_active: false, invitation_status: 'pending' }], total: 1, next_cursor: null, has_more: false } });
  render(<PeopleDirectory user={user} />);
  await visitor.click(await screen.findByRole('button', { name: 'Actions for Person' }));
  expect(await screen.findByRole('menuitem', { name: 'Resend invitation' })).toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: 'Enable' })).not.toBeInTheDocument();
});
it('hides mutations from platform readers', async () => {
  render(<PeopleDirectory user={{ ...user, contextId: 'platform', role: 'platform_admin', permissions: ['platform.users.read'] }} />);
  await screen.findByRole('link', { name: 'Person' });
  expect(screen.queryByRole('button', { name: 'Create user' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument();
});
it('shows one-time invitation links only when email was not delivered', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [{ ...row, user_id: null, invitation_status: 'pending', is_active: false }], total: 1, next_cursor: null, has_more: false } });
  vi.mocked(actions.managePerson).mockResolvedValue({ value: { person: row, email_delivered: false, invitation_token: 'inv_test-only-link' } });
  render(<PeopleDirectory user={user} />);
  await visitor.click(await screen.findByRole('button', { name: 'Actions for Person' }));
  await visitor.click(await screen.findByRole('menuitem', { name: 'Resend invitation' }));
  await visitor.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Resend invitation' }));
  const link = await screen.findByLabelText('Invitation link');
  expect((link as HTMLInputElement).value).toContain('/invitations/accept#token=inv_test-only-link');
  await visitor.click(screen.getByRole('button', { name: 'Done' }));
  expect(screen.queryByLabelText('Invitation link')).not.toBeInTheDocument();
  expect(screen.queryByText('Invitation sent by email.')).not.toBeInTheDocument();
});
it('shows manual account setup and invitation links together after creation', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.savePerson).mockResolvedValue({ value: { person: { ...row, email: 'new@example.com' }, setup_queued: true, setup_token: 'act_private-link', email_delivered: false, invitation_token: 'inv_private-link' } });
  render(<PeopleDirectory user={{ ...user, contextId: 'platform', role: 'platform_admin', permissions: ['platform.users.read', 'platform.users.manage', 'platform.administrators.manage'] }} />);
  await visitor.click(await screen.findByRole('button', { name: 'Create user' }));
  const editor = screen.getByRole('dialog', { name: 'Create user' });
  await visitor.type(within(editor).getByLabelText('Display name'), 'New');
  await visitor.type(within(editor).getByLabelText('Email address'), 'new@example.com');
  await visitor.selectOptions(within(editor).getByLabelText('Administrator role'), 'platform_admin');
  await visitor.click(within(editor).getByRole('button', { name: 'Create user' }));
  expect((await screen.findByLabelText('Account setup link') as HTMLInputElement).value).toContain('/account/setup#token=act_private-link');
  expect((screen.getByLabelText('Invitation link') as HTMLInputElement).value).toContain('/invitations/accept#token=inv_private-link');
  await visitor.click(screen.getByRole('button', { name: 'Done' }));
  expect(screen.queryByLabelText('Account setup link')).not.toBeInTheDocument();
});
it('disables self-disable and self-archive in the directory and leaves other accounts manageable', async () => {
  const permissions = ['platform.users.read', 'platform.users.manage', 'platform.administrators.manage'];
  const self = { ...row, id: user.id, display_name: 'My account', platform_role: 'platform_admin' as const };
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [self, { ...row, tenant_admin: true }], total: 2, next_cursor: null, has_more: false } });
  render(<PeopleDirectory user={{ ...user, role: 'platform_admin', contextId: 'platform', permissions }} />);
  const ownRow = (await screen.findByRole('link', { name: 'My account' })).closest('tr')!;
  expect(within(ownRow).getByRole('button', { name: 'Disable' })).toBeDisabled();
  expect(within(ownRow).getByRole('button', { name: 'Archive' })).toBeDisabled();
  expect(within(ownRow).getByRole('button', { name: 'Edit' })).toBeEnabled();
  const otherRow = screen.getByRole('link', { name: 'Person' }).closest('tr')!;
  expect(within(otherRow).getByRole('button', { name: 'Archive' })).toBeEnabled();
  expect(within(otherRow).getByText('Tenant administrator')).toBeInTheDocument();
});
it('also protects self-actions on a deep-linked user detail', async () => {
  vi.mocked(actions.readPerson).mockResolvedValue({ value: { ...row, id: user.id, platform_role: 'platform_admin' } });
  render(<PeopleDirectory memberId={user.id} user={{ ...user, role: 'platform_admin', contextId: 'platform', permissions: ['platform.users.read', 'platform.users.manage', 'platform.administrators.manage'] }} />);
  expect(await screen.findByRole('button', { name: 'Disable' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled();
});
it('disables self-actions for tenant memberships in the list and direct detail', async () => {
  const visitor = userEvent.setup();
  const self = { ...row, id: 'own-membership', user_id: user.id, role: 'org_admin' as const, display_name: 'My tenant access' };
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [self, row], total: 2, next_cursor: null, has_more: false } });
  render(<PeopleDirectory user={user} />);
  const ownRow = (await screen.findByRole('link', { name: 'My tenant access' })).closest('tr')!;
  await visitor.click(within(ownRow).getByRole('button', { name: 'Actions for My tenant access' }));
  expect(await screen.findByRole('menuitem', { name: /Disable/ })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem', { name: /Archive/ })).toHaveAttribute('aria-disabled', 'true');
  await visitor.keyboard('{Escape}');
  const otherRow = screen.getByRole('link', { name: 'Person' }).closest('tr')!;
  await visitor.click(within(otherRow).getByRole('button', { name: 'Actions for Person' }));
  expect(await screen.findByRole('menuitem', { name: 'Disable' })).not.toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('menuitem', { name: 'Archive' })).not.toHaveAttribute('aria-disabled', 'true');
});

it('clears filters back to the server defaults and distinguishes a filtered empty list', async () => {
  const visitor = userEvent.setup();
  render(<PeopleDirectory user={user} />);
  await screen.findByRole('link', { name: 'Person' });
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [], total: 0, next_cursor: null, has_more: false } });
  await visitor.selectOptions(screen.getByLabelText('Role filter'), 'org_trainee');
  expect(await screen.findByText('No matching people')).toBeInTheDocument();
  expect(actions.listPeople).toHaveBeenLastCalledWith('tenant', expect.objectContaining({ role: 'org_trainee' }), undefined);
  await visitor.click(screen.getAllByRole('button', { name: 'Clear filters' })[0]!);
  expect(await screen.findByText('Build your team')).toBeInTheDocument();
  expect(screen.getByLabelText('Role filter')).toHaveValue('');
  expect(actions.listPeople).toHaveBeenLastCalledWith('tenant', expect.objectContaining({ role: '', q: '', state: 'current' }), undefined);
});

it('opens the invitation drawer from the empty state and provides import history navigation', async () => {
  const visitor = userEvent.setup();
  vi.mocked(actions.listPeople).mockResolvedValue({ value: { items: [], total: 0, next_cursor: null, has_more: false } });
  render(<PeopleDirectory user={user} />);
  await visitor.click(await screen.findByRole('button', { name: 'Invite your first member' }));
  expect(screen.getByRole('dialog', { name: 'Invite member' })).toBeInTheDocument();
  await visitor.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
  expect(screen.getByRole('link', { name: 'Import history' })).toHaveAttribute('href', '/members/import/history');
});
it('protects a deep-linked tenant membership even when it is not in the list', async () => {
  vi.mocked(actions.readPerson).mockResolvedValue({ value: { ...row, id: 'own-membership', user_id: user.id, role: 'org_admin' } });
  render(<PeopleDirectory user={user} memberId="own-membership" />);
  expect(await screen.findByRole('button', { name: 'Disable' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled();
});
