import type { Metadata } from 'next';
import { PeopleDirectory } from '@/components/PeopleDirectory';
import { requireSettingsSection } from '@/lib/settings-access';
import { currentUser } from '@/lib/session';
export const metadata: Metadata = { title: 'User details' };
export default async function Page({ params }: { params: Promise<{ userId: string }> }) {
  await requireSettingsSection('users');
  const user = await currentUser();
  if (!user) return null;
  const { userId } = await params;
  return <PeopleDirectory key={user.contextId + userId} user={user} memberId={userId} />;
}
