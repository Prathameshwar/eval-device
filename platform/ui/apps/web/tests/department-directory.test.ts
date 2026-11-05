import { describe, expect, it } from 'vitest';
import { DEMO_DEPARTMENTS } from '../src/data/departments';
import {
  archiveDepartment,
  DEFAULT_DEPARTMENT_QUERY,
  departmentPage,
  departmentStatus,
  type Department
} from '../src/lib/department-directory';

describe('department directory queries', () => {
  it('searches the whole dataset by name and description with case-insensitive substrings', () => {
    const result = departmentPage(DEMO_DEPARTMENTS, { ...DEFAULT_DEPARTMENT_QUERY, q: ' cardio ' }, 0);
    expect(result.total).toBeGreaterThan(0);
    expect(result.items.every((row) => row.name.startsWith('Cardio'))).toBe(true);
  });

  it('filters by active and inactive status', () => {
    const active = departmentPage(DEMO_DEPARTMENTS, { ...DEFAULT_DEPARTMENT_QUERY, is_active: true }, 0);
    expect(active.total).toBeGreaterThan(0);
    expect(active.items.every((row) => row.is_active)).toBe(true);

    const inactive = departmentPage(DEMO_DEPARTMENTS, { ...DEFAULT_DEPARTMENT_QUERY, is_active: false }, 0);
    expect(inactive.total).toBeGreaterThan(0);
    expect(inactive.items.every((row) => !row.is_active)).toBe(true);
  });

  it('filters by archived state', () => {
    const archived = departmentPage(DEMO_DEPARTMENTS, { ...DEFAULT_DEPARTMENT_QUERY, archived: true }, 0);
    expect(archived.items.every((row) => departmentStatus(row) === 'archived')).toBe(true);
  });

  it('walks matching rows in stable order', () => {
    const query = { ...DEFAULT_DEPARTMENT_QUERY };
    const result = departmentPage(DEMO_DEPARTMENTS, query, 0);
    const ids = result.items.map((row) => row.id);
    expect(ids).toHaveLength(result.items.length);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('archives locally and increments management version', () => {
    const dept = DEMO_DEPARTMENTS[0]!;
    expect(dept.archived_at).toBeNull();
    const archived = archiveDepartment(dept, '2026-09-22T12:00:00Z');
    expect(archived.archived_at).toBe('2026-09-22T12:00:00Z');
    expect(archived.is_active).toBe(false);
    expect(archived.management_version).toBe(dept.management_version + 1);

    expect(archiveDepartment(archived, 'ignored')).toBe(archived); // should not re-archive
  });
});
