import { redirect } from 'next/navigation';
import { requireSettingsSection } from '@/lib/settings-access';
import { PlatformOptions } from '@/components/PlatformOptions';
export default async function Page() {
  const user = await requireSettingsSection('platform-options');
  if (user.contextId !== 'platform') redirect('/home');
  return <PlatformOptions canManage={user.permissions.includes('platform.settings.manage')} />;
}
