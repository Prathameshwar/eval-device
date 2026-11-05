import type { Metadata } from 'next';
import { MemberImportWizard } from '@/components/MemberImportWizard';
import { requireMemberManage } from '@/lib/member-access';

export const metadata: Metadata = { title: 'Import members' };
export default async function Page({ searchParams }: { searchParams: Promise<{ batch?: string }> }) {
  const user = await requireMemberManage();
  const { batch } = await searchParams;
  return <MemberImportWizard key={user.contextId} contextId={user.contextId!}
    tenantName={user.tenant?.name ?? 'Your tenant'} initialId={batch} />;
}
