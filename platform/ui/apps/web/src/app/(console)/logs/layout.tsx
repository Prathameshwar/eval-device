import type { ReactNode } from 'react';
import { LogDirectoryProvider } from '@/components/LogDirectoryProvider';
import { requireLogRead } from '@/lib/log-access';

export default async function LogLayout({ children }: { children: ReactNode }) {
  const user = await requireLogRead();
  return (
    <LogDirectoryProvider key={user.contextId} user={user}>
      {children}
    </LogDirectoryProvider>
  );
}
