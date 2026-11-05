import type { Metadata } from 'next';
import { PeopleDirectory } from '@/components/PeopleDirectory';
import { requireMemberManage } from '@/lib/member-access';

export const metadata: Metadata = { title: 'Member details' };

export default async function Page({ params }: { params: Promise<{ memberId: string }> }) {
  const user = await requireMemberManage();
  const { memberId } = await params;
  return <PeopleDirectory key={user.contextId + memberId} memberId={memberId} user={user} />;
}
