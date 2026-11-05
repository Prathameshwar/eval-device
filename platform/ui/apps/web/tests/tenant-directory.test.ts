import { describe, expect, it } from 'vitest';
import { DEMO_TENANTS } from '../src/data/tenants';
import { archiveTenant, DEFAULT_TENANT_QUERY, tenantPage, tenantStatus, type Tenant } from '../src/lib/tenant-directory';

describe('tenant directory queries', () => {
  it('searches the whole dataset by name with literal, case-insensitive substrings', () => {
    const result = tenantPage(DEMO_TENANTS, { ...DEFAULT_TENANT_QUERY, q: ' wiLLoW ' }, 0);
    expect(result.total).toBeGreaterThan(0);
    expect(result.items.every((row) => row.name.startsWith('Willow'))).toBe(true);
    expect(tenantPage(DEMO_TENANTS, { ...DEFAULT_TENANT_QUERY, q: '%' }, 0).total).toBe(0);
    expect(tenantPage(DEMO_TENANTS, { ...DEFAULT_TENANT_QUERY, q: '@example.com' }, 0).total).toBe(0);
  });

  it('combines lifecycle and activity predicates without treating inactive as archived', () => {
    const inactive = tenantPage(DEMO_TENANTS, { ...DEFAULT_TENANT_QUERY, is_active: false }, 0);
    expect(inactive.total).toBeGreaterThan(0);
    expect(inactive.items.every((row) => !row.is_active && !row.archived_at)).toBe(true);
    const archived = tenantPage(DEMO_TENANTS, { ...DEFAULT_TENANT_QUERY, archived: true }, 0);
    expect(archived.items.every((row) => tenantStatus(row) === 'archived')).toBe(true);
    expect(tenantPage(DEMO_TENANTS, { ...DEFAULT_TENANT_QUERY, archived: true, is_active: true }, 0).total).toBe(0);
  });

  it('walks all matching rows without duplicates, in stable order', () => {
    const query = { ...DEFAULT_TENANT_QUERY, archived: undefined };
    const ids = [0, 1, 2].flatMap((page) => tenantPage(DEMO_TENANTS, query, page).items.map((row) => row.id));
    expect(ids).toHaveLength(68);
    expect(new Set(ids).size).toBe(68);
    expect(tenantPage(DEMO_TENANTS, query, 2).has_more).toBe(false);
    expect(tenantPage(DEMO_TENANTS, query, 1).from).toBe(26);
    const descending = tenantPage(DEMO_TENANTS, { ...query, sort_order: 'desc', limit: 100 }, 0);
    expect(descending.items.map((row) => row.id)).toEqual([...ids].reverse());
  });

  it('uses ID as a tie-breaker and leaves fixture ordering untouched', () => {
    const a = { ...DEMO_TENANTS[0]!, name: 'Same tenant' };
    const b = { ...DEMO_TENANTS[1]!, name: 'Same tenant' };
    const rows = [b, a];
    expect(tenantPage(rows, DEFAULT_TENANT_QUERY, 0).items.map((row) => row.id)).toEqual([a.id, b.id]);
    expect(rows).toEqual([b, a]);
  });

  it('archives locally, preserves the record, and clamps an emptied final page', () => {
    const rows = Array.from({ length: 26 }, (_, index): Tenant => ({
      ...DEMO_TENANTS[0]!, id: String(index), name: String(index).padStart(2, '0'),
    }));
    const updated = rows.map((row, index) => index === 25 ? archiveTenant(row, '2026-09-22T10:00:00Z') : row);
    const result = tenantPage(updated, DEFAULT_TENANT_QUERY, 1);
    expect(result.page).toBe(0);
    expect(result.items).toHaveLength(25);
    expect(updated).toHaveLength(26);
    expect(updated[25]?.is_active).toBe(false);
    expect(updated[25]?.management_version).toBe(2);
    expect(archiveTenant(updated[25]!, '2026-09-23T00:00:00Z')).toBe(updated[25]);
    expect(rows[25]?.archived_at).toBeNull();
  });
});
