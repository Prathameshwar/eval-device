import type { Metadata } from 'next';
import { PeopleDirectory } from '@/components/PeopleDirectory';
import { requireSettingsSection } from '@/lib/settings-access';
import { currentUser } from '@/lib/session';

export const metadata: Metadata = { title: 'Users & administrators' };

export default async function Page() {
  await requireSettingsSection('users');
  const user = await currentUser();
  if (!user) return null;
  return <PeopleDirectory key={user.contextId} user={user} />;
}
