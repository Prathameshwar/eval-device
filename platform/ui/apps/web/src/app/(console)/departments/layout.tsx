import type { ReactNode } from 'react';
import { requireDepartmentManage } from '@/lib/department-access';
export default async function Layout({ children }: { children: ReactNode }) {
  await requireDepartmentManage();
  return <>{children}</>;
}
