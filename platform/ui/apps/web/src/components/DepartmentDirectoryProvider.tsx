'use client';

import { createContext, useContext, useRef, useState, type ReactNode } from 'react';
import { useGranted } from '@pms/ui';
import { archiveDepartment, DEFAULT_DEPARTMENT_QUERY, departmentPage, type Department, type DepartmentQuery } from '@/lib/department-directory';
import { saveDepartmentDraft, validateDepartmentDraft, type DepartmentDraft } from '@/lib/department-editor';

type SavedDepartment = { id: string; name: string; created: boolean };
type SaveResult = { department: Department; error?: never } | { department?: never; error: string };

function useDirectoryState(initialRows: readonly Department[]) {
  const [rows, setRows] = useState(initialRows);
  const [query, setQuery] = useState<DepartmentQuery>(DEFAULT_DEPARTMENT_QUERY);
  const [pageIndex, setPageIndex] = useState(0);
  const [savedDepartment, setSavedDepartment] = useState<SavedDepartment | null>(null);
  const listBookmark = useRef<{ id: string; tableTop: number; pageTop: number } | null>(null);
  const granted = useGranted();
  
  // Gated on org.departments.manage
  const canManage = granted('org.departments.manage') || granted('platform.organizations.manage');

  function save(draft: DepartmentDraft, original: Department | null): SaveResult {
    if (!canManage) return { error: 'You do not have permission to edit departments.' };
    const current = original ? rows.find((row) => row.id === original.id) : null;
    if (original && (!current || current.archived_at || current.management_version !== original.management_version)) {
      return { error: 'This department has changed or is archived. Cancel and reopen it.' };
    }
    if (Object.keys(validateDepartmentDraft(draft)).length) {
      return { error: 'Check the department details before saving.' };
    }
    const department = saveDepartmentDraft(draft, current ?? null, current?.id ?? crypto.randomUUID(), new Date().toISOString());
    const next = current ? rows.map((row) => row.id === department.id ? department : row) : [department, ...rows];
    setRows(next);
    setPageIndex(departmentPage(next, query, pageIndex).page);
    setSavedDepartment({ id: department.id, name: department.name, created: !current });
    return { department };
  }

  function archive(original: Department): string | undefined {
    if (!canManage) return 'You do not have permission to archive departments.';
    const current = rows.find((row) => row.id === original.id);
    if (!current || current.archived_at || current.management_version !== original.management_version) {
      return 'This department has changed. Cancel and reopen it before trying again.';
    }
    const next = rows.map((row) => row.id === current.id ? archiveDepartment(row, new Date().toISOString()) : row);
    setRows(next);
    setPageIndex(departmentPage(next, query, pageIndex).page);
    setSavedDepartment(null);
    return undefined;
  }

  return { rows, query, setQuery, pageIndex, setPageIndex, savedDepartment, setSavedDepartment, listBookmark, save, archive };
}

const DirectoryContext = createContext<ReturnType<typeof useDirectoryState> | null>(null);

export function DepartmentDirectoryProvider({ initialRows, children }: {
  initialRows: readonly Department[];
  children: ReactNode;
}) {
  const state = useDirectoryState(initialRows);
  return <DirectoryContext.Provider value={state}>{children}</DirectoryContext.Provider>;
}

export function useDepartmentDirectory() {
  const state = useContext(DirectoryContext);
  if (!state) throw new Error('Department pages require DepartmentDirectoryProvider.');
  return state;
}
