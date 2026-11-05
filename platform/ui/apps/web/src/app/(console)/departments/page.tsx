import { ManagedDepartments } from '@/components/ManagedDepartments';
import { requireDepartmentManage } from '@/lib/department-access';
export default async function Page() {
  const user = await requireDepartmentManage();
  return <ManagedDepartments key={user.contextId} contextId={user.contextId!} />;
}
