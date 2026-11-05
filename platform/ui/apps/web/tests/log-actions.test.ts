import { beforeEach, expect, it, vi } from 'vitest';
import { apiRequest } from '../src/lib/api';
import { currentUser, sessionToken } from '../src/lib/session';
import { listLogs, readLog } from '../src/lib/log-actions';
import { defaultLogQuery } from '../src/lib/log-directory';
import { logUser, tenantId, logRecord, logPage } from './fixtures/logs';
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn(), sessionToken: vi.fn() }));
vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), apiRequest: vi.fn() }));
beforeEach(() => {
  vi.mocked(currentUser).mockResolvedValue(logUser); vi.mocked(sessionToken).mockResolvedValue('test-session');
  vi.mocked(apiRequest).mockReset(); vi.mocked(apiRequest).mockResolvedValue(logPage);
});
it('sends inclusive UTC days as an exclusive end and binds pagination to the query', async () => {
  await listLogs(tenantId, { ...defaultLogQuery('all'), since: '2026-09-23', until: '2026-09-24', severity: 'warning' }, 'signed');
  const url = new URL(vi.mocked(apiRequest).mock.calls[0]![0], 'http://test');
  expect(url.pathname).toBe('/organizations/' + tenantId + '/activities');
  expect(Object.fromEntries(url.searchParams)).toMatchObject({ since: '2026-09-23T00:00:00.000Z', until: '2026-09-25T00:00:00.000Z', include_total: 'true', cursor: 'signed', severity: 'warning' });
});
it('requires the exact platform audit grant', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...logUser, contextId: 'platform', role: 'platform_admin', permissions: ['platform.organizations.read'] });
  expect((await listLogs('platform', defaultLogQuery('audit'))).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('does not let platform or activity-only users request tenant audits', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...logUser, permissions: ['org.activity.read'] });
  expect((await listLogs(tenantId, defaultLogQuery('all'))).error).toMatch(/permission/);
  expect((await listLogs(tenantId, defaultLogQuery('audit'))).error).toMatch(/permission/);
  expect(apiRequest).not.toHaveBeenCalled();
});
it('fences an old tab after context changes', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...logUser, contextId: 'another' });
  expect((await readLog(tenantId, logRecord.id)).error).toMatch(/tenant changed/); expect(apiRequest).not.toHaveBeenCalled();
});
it.each([{ since: '2026-02-30' }, { since: '2026-09-25', until: '2026-09-24' }, { device_id: '../devices' }])('rejects invalid filters %s', async filters => {
  expect((await listLogs(tenantId, { ...defaultLogQuery('all'), ...filters })).error).toBeDefined();
  expect(apiRequest).not.toHaveBeenCalled();
});
it('loads direct details without relying on a loaded directory page', async () => {
  await readLog(tenantId, logRecord.id);
  expect(apiRequest).toHaveBeenCalledWith('/organizations/' + tenantId + '/activities/' + logRecord.id, { token: 'test-session' });
});
it('requires authentication and valid detail IDs', async () => {
  expect((await readLog(tenantId, '../audit')).error).toBeDefined();
  vi.mocked(currentUser).mockResolvedValue(undefined);
  expect((await readLog(tenantId, logRecord.id)).error).toBeDefined(); expect(apiRequest).not.toHaveBeenCalled();
});
it('routes platform queries to audit only with tenant ID filtering', async () => {
  vi.mocked(currentUser).mockResolvedValue({ ...logUser, contextId: 'platform', role: 'platform_admin', permissions: ['platform.audit.read'] });
  await listLogs('platform', { ...defaultLogQuery('audit'), organization_id: tenantId });
  expect(vi.mocked(apiRequest).mock.calls[0]![0]).toContain('/platform/audit?');
  expect(vi.mocked(apiRequest).mock.calls[0]![0]).toContain('organization_id=' + tenantId);
});
