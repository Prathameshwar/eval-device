import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { PersonalSettings } from '@/components/PersonalSettings';
import { SettingsHub } from '@/components/SettingsHub';
import { currentUser } from '@/lib/session';
import { canOpenSettings, settingsFor } from '@/lib/settings';

export const metadata: Metadata = { title: 'Settings' };

export default async function Page() {
  const user = await currentUser();
  if (!user) redirect('/login');
  const granted = (permission: string) => user.permissions.includes(permission);
  if (!canOpenSettings(user.role, granted)) redirect('/home');
  // Personal settings edit the signed-in user; management cards are role-scoped.
  if (user.role === 'org_user') return <PersonalSettings />;
  return <SettingsHub sections={settingsFor(user.role, granted)} tenantScoped={user.role === 'org_admin'} />;
}
