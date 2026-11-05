'use client';
import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import type { SessionUser } from '@/lib/session-user';
import { defaultLogQuery, logCategories, type LogQuery } from '@/lib/log-directory';
import { listLogs } from '@/lib/log-actions';
import { useApiDirectory } from '@/lib/use-api-directory';

function useDirectoryState(user: SessionUser) {
  const categories = useMemo(() => logCategories(user), [user]);
  const fetchPage = useCallback((query: LogQuery, cursor?: string) => listLogs(user.contextId!, query, cursor), [user.contextId]);
  const directory = useApiDirectory(defaultLogQuery(categories[0] ?? 'operational'), fetchPage);
  return { ...directory, user, categories, canRead: categories.length > 0 };
}
const DirectoryContext = createContext<ReturnType<typeof useDirectoryState> | null>(null);
export function LogDirectoryProvider({ user, children }: { user: SessionUser; children: ReactNode }) {
  const state = useDirectoryState(user);
  return <DirectoryContext.Provider value={state}>{children}</DirectoryContext.Provider>;
}
export function useLogDirectory() {
  const state = useContext(DirectoryContext);
  if (!state) throw new Error('Log pages require LogDirectoryProvider.');
  return state;
}
