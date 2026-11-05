import { redirect } from 'next/navigation';
import { PermissionProvider } from '@pms/ui';
import { ConsoleShell } from '@/components/ConsoleShell';
import { SessionWatcher } from '@/components/SessionWatcher';
import { NOTIFICATION_COUNT } from '@/data/demo';
import { currentUser } from '@/lib/session';

/**
 * The API verifies the opaque session and supplies the selected context's current grants.
 * Pages also check currentUser because Next may retain layouts during navigation.
 * PermissionProvider controls presentation; API operations enforce their own authorization.
 */
export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  if (!user) redirect('/login');

  return (
    <PermissionProvider permissions={user.permissions}>
      <SessionWatcher />
      <ConsoleShell user={user} notifications={NOTIFICATION_COUNT}>
        {children}
      </ConsoleShell>
    </PermissionProvider>
  );
}
