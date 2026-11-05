import { describe, expect, it } from 'vitest';
import { defaultLogQuery, logCategories, logDate } from '../src/lib/log-directory';
import { logUser } from './fixtures/logs';
describe('log access and date filters', () => {
  it('uses exact grants in the selected context', () => {
    expect(logCategories(logUser)).toEqual(['all', 'audit', 'operational']);
    expect(logCategories({ ...logUser, permissions: ['org.activity.read'] })).toEqual(['operational']);
    expect(logCategories({ ...logUser, permissions: ['org.audit.read'] })).toEqual(['audit']);
    expect(logCategories({ ...logUser, contextId: 'platform', permissions: ['platform.organizations.read'] })).toEqual([]);
    expect(logCategories({ ...logUser, contextId: 'platform', permissions: ['platform.audit.read'] })).toEqual(['audit']);
    expect(logCategories({ ...logUser, contextId: undefined })).toEqual([]);
  });
  it('defaults to recent events and a bounded page', () => {
    expect(defaultLogQuery('audit')).toMatchObject({ category: 'audit', sort_by: 'occurred_at', sort_order: 'desc', limit: 25 });
  });
  it('uses UTC days with an inclusive through-day', () => {
    expect(logDate('2026-09-24')).toBe('2026-09-24T00:00:00.000Z');
    expect(logDate('2026-12-31', true)).toBe('2027-01-01T00:00:00.000Z');
    expect(logDate('')).toBeUndefined();
  });
  it.each(['2026-02-30', 'not-a-date', '2026-09-24T10:00:00Z'])('rejects invalid date %s', date => expect(() => logDate(date)).toThrow());
});
