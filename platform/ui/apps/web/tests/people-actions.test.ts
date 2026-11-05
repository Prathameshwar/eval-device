import { beforeEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/lib/api';
import { currentUser, sessionToken } from '../src/lib/session';
import { listPeople, managePerson, peopleTenants, readPerson, savePerson } from '../src/lib/people-actions';
import { peopleQuery, personDraft } from '../src/lib/people';
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), apiRequest: vi.fn() }));
const id = '12345678-1234-4234-8234-123456789012';
const user = { id: 'user', name: 'Owner', email: 'owner@example.com', role: 'org_admin' as const, contextId: id, permissions: ['org.members.manage'] };
beforeEach(() => {
  vi.mocked(currentUser).mockResolvedValue(user); vi.mocked(sessionToken).mockResolvedValue('web_private');
  vi.mocked(apiRequest).mockReset(); vi.mocked(apiRequest).mockResolvedValue({ id, invitation_status: 'accepted' });
});
it('requires tenant membership permissions even for a platform administrator', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, role: 'platform_admin', contextId: 'platform', permissions: ['platform.organizations.read', 'platform.users.manage'] });
  expect((await listPeople(id, peopleQuery(false))).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('rejects mutations from a tab whose selected tenant changed', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, contextId: 'other' });
  expect((await savePerson(id, personDraft(false), id, 2)).error).toMatch(/tenant changed/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it.each(['archive', 'revoke', 'resend'] as const)('fences %s with a version', async action => {
  vi.mocked(apiRequest).mockResolvedValue({ id, membership: { id } });
  await managePerson(id, id, action, 7);
  expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining('expected_version=7'), expect.anything());
});
it('rejects missing versions and unsupported member operations without a request', async () => {
  await savePerson(id, personDraft(false), id);
  await managePerson(id, id, 'setup', 3);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('updates tenant access without modifying global identity or pre-accepting invitations', async () => {
  await savePerson(id, { ...personDraft(false), display_name: 'Not global', email: 'changed@example.com' }, id, 3);
  expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining('/members/'), expect.objectContaining({ method: 'PATCH', body: {
    expected_version: 3, role: 'org_user', department_id: null, status_reason: null,
  } }));
});
it('creates bound local invitations and preserves the one-time manual links', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ membership: { id, invited_email: 'new@example.com' }, email_delivered: false, invitation_token: 'inv_test-only', setup_token: 'act_test-only' });
  const result = await savePerson(id, { ...personDraft(false), display_name: 'New', email: 'new@example.com' });
  expect(apiRequest).toHaveBeenCalledWith(expect.stringContaining('/invitations'), expect.objectContaining({ body: expect.objectContaining({ auth_method: 'local', local_display_name: 'New' }) }));
  expect(result.value).toMatchObject({ email_delivered: false, invitation_token: 'inv_test-only', setup_token: 'act_test-only', person: { email: 'new@example.com' } });
});
it('filters enabled members to accepted memberships and binds signed cursors', async () => {
  vi.mocked(apiRequest).mockResolvedValue({ items: [], total: 0 });
  await listPeople(id, { ...peopleQuery(false), state: 'enabled' }, 'cursor');
  const url = vi.mocked(apiRequest).mock.calls[0]![0];
  expect(url).toContain('invitation_status=accepted'); expect(url).toContain('is_active=true'); expect(url).toContain('cursor=cursor');
});
it('validates identifiers before requesting details', async () => {
  expect((await readPerson(id, '../users')).error).toBeDefined(); expect(apiRequest).not.toHaveBeenCalled();
});
it('requires administrator permission for administrator creation', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, role: 'platform_admin', contextId: 'platform', permissions: ['platform.users.manage'] });
  expect((await savePerson('platform', { ...personDraft(true), role: 'platform_admin' })).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('creates tenant administrators in one request and retains the invitation delivery result', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, contextId: 'platform', permissions: ['platform.users.manage', 'platform.organization_admins.manage'] });
  vi.mocked(apiRequest).mockResolvedValue({ user: { id, tenant_admin: true }, email_delivered: false, invitation_token: 'inv_fixture', setup_token: 'act_fixture' });
  const result = await savePerson('platform', { ...personDraft(true), display_name: 'New admin', email: 'admin@example.com', role: 'org_admin', organization_id: id });
  expect(apiRequest).toHaveBeenCalledOnce();
  expect(apiRequest).toHaveBeenCalledWith('/platform/users', expect.objectContaining({ method: 'POST', body: {
    display_name: 'New admin', phone: null, email: 'admin@example.com', organization_id: id,
  } }));
  expect(result.value).toMatchObject({ setup_queued: true, email_delivered: false, invitation_token: 'inv_fixture', setup_token: 'act_fixture', person: { tenant_admin: true } });
});
it('checks tenant assignment permission and tenant selection before sending a creation request', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, contextId: 'platform', permissions: ['platform.users.manage', 'platform.administrators.manage'] });
  const draft = { ...personDraft(true), role: 'org_admin', organization_id: id };
  expect((await savePerson('platform', draft)).error).toMatch(/permission/);
  vi.mocked(currentUser).mockResolvedValue({ ...user, contextId: 'platform', permissions: ['platform.users.manage', 'platform.organization_admins.manage'] });
  expect((await savePerson('platform', { ...draft, organization_id: '' })).error).toMatch(/Select a tenant/);
  expect((await savePerson('platform', { ...draft, organization_id: '../other' })).error).toBeDefined();
  expect((await savePerson('platform', { ...draft, role: 'org_trainee' })).error).toMatch(/Choose Platform administrator/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('blocks self-disable and self-archive through both server action paths', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, id, contextId: 'platform', permissions: ['platform.users.manage', 'platform.administrators.manage'] });
  for (const action of ['disable', 'archive'] as const) expect((await managePerson('platform', id, action, 3)).error).toMatch(/own account/);
  expect((await savePerson('platform', { ...personDraft(true), role: 'platform_admin', is_active: false }, id, 3)).error).toMatch(/own account/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('loads tenant choices through platform permissions and follows pagination', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...user, contextId: 'platform', permissions: ['platform.organization_admins.manage', 'platform.organizations.read'] });
  vi.mocked(apiRequest).mockResolvedValueOnce({ items: [{ id }], next_cursor: 'next' }).mockResolvedValueOnce({ items: [{ id: 'second' }], next_cursor: null });
  expect((await peopleTenants()).value).toEqual([{ id }, { id: 'second' }]);
  expect(apiRequest).toHaveBeenNthCalledWith(2, expect.stringContaining('archived=false&limit=100&cursor=next'), { token: 'web_private' });
});
