import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { TenantProvisionWizard } from '@/components/TenantProvisionWizard';
import { currentUser } from '@/lib/session';

export const metadata: Metadata = { title: 'Create tenant' };
export default async function Page() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!['platform.organizations.manage', 'platform.organization_admins.manage', 'platform.users.manage'].every(permission => user.permissions.includes(permission))) redirect('/home');
  return <TenantProvisionWizard />;
}
