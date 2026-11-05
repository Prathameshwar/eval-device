import { beforeEach, expect, it, vi } from 'vitest';
import { currentUser, sessionToken } from '../src/lib/session';
import { commitMemberImport, memberImportHistory, readMemberImport, validateMemberImport } from '../src/lib/member-import-actions';
import { GET } from '../src/app/api/member-imports/download/route';
import { importOptions } from '../src/lib/member-imports';
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
const id = '11111111-1111-4111-8111-111111111111';
const tenant = { id: 'actor', name: 'Admin', email: 'a@example.com', role: 'org_admin' as const, contextId: id, permissions: ['org.members.manage'] };
const request = vi.fn();
beforeEach(() => {
  vi.stubGlobal('fetch', request); request.mockReset();
  vi.mocked(currentUser).mockResolvedValue(tenant);
  vi.mocked(sessionToken).mockResolvedValue('private_session');
});
it('rejects a changed tenant or missing permission before making a request', async () => {
  expect((await memberImportHistory('22222222-2222-4222-8222-222222222222')).error).toMatch(/tenant changed/);
  vi.mocked(currentUser).mockResolvedValue({ ...tenant, permissions: [] });
  expect((await commitMemberImport(id, id)).error).toMatch(/permission/);
  expect(request).not.toHaveBeenCalled();
});
it('commits a saved batch through the tenant endpoint, keeping credentials server-side', async () => {
  request.mockResolvedValue(new Response(JSON.stringify({ id, status: 'completed' })));
  expect((await commitMemberImport(id, id)).value).toEqual({ id, status: 'completed' });
  expect(request).toHaveBeenCalledWith(expect.stringContaining('/organizations/' + id + '/member-imports/' + id + '/commit'),
    expect.objectContaining({ method: 'POST', redirect: 'error', cache: 'no-store', headers: { Authorization: 'Bearer private_session' } }));
});
it('rejects forged roles and invalid resource identifiers', async () => {
  expect(() => importOptions({ role: 'platform_admin' as never, auth_method: 'local', department_id: '' })).toThrow();
  expect((await readMemberImport(id, '../users')).error).toBeDefined();
  const form = new FormData();
  form.set('file', new File(['bad'], 'bad.csv'));
  expect((await validateMemberImport(id, { role: 'org_user', auth_method: 'local', department_id: '' }, form)).error).toBeDefined();
  expect(request).not.toHaveBeenCalled();
});
it('binary downloads are authenticated, no-store, and confined to fixed routes', async () => {
  request.mockResolvedValue(new Response('xlsx', { status: 200 }));
  const response = await GET(new Request('http://localhost/api/member-imports/download?context=' + id + '&kind=errors&id=' + id));
  expect(response.status).toBe(200);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(response.headers.get('Content-Disposition')).toContain('member-import-errors.xlsx');
  expect(await response.text()).toBe('xlsx');
  request.mockClear();
  const invalid = await GET(new Request('http://localhost/api/member-imports/download?context=' + id + '&kind=https://evil.example'));
  expect(invalid.status).toBe(422);
  expect(request).not.toHaveBeenCalled();
});
