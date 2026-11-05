import type { Metadata } from 'next';
import { PeopleDirectory } from '@/components/PeopleDirectory';
import { requireMemberManage } from '@/lib/member-access';

export const metadata: Metadata = { title: 'Members' };

export default async function Page() {
  const user = await requireMemberManage();
  return <PeopleDirectory key={user.contextId} user={user} />;
}
