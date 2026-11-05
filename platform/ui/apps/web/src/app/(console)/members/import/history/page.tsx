import type { Metadata } from 'next';
import { MemberImportHistory } from '@/components/MemberImportHistory';
import { requireMemberManage } from '@/lib/member-access';

export const metadata: Metadata = { title: 'Import History' };
export default async function Page() {
  const user = await requireMemberManage();
  return <MemberImportHistory key={user.contextId} contextId={user.contextId!} />;
}
