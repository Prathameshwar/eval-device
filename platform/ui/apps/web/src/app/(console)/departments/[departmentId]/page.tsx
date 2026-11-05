import { ManagedDepartments } from '@/components/ManagedDepartments';
import { requireDepartmentManage } from '@/lib/department-access';
export default async function Page({ params }: { params: Promise<{ departmentId: string }> }) {
  const user = await requireDepartmentManage();
  const { departmentId: id } = await params;
  return <ManagedDepartments key={user.contextId + id} contextId={user.contextId!} id={id} />;
}
