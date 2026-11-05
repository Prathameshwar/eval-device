import type { ReactNode } from 'react';
import { requireMemberManage } from '@/lib/member-access';

export default async function MemberLayout({ children }: { children: ReactNode }) {
  await requireMemberManage();
  return <>{children}</>;
}
