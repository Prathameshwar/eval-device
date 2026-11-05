import { redirect } from 'next/navigation';
import { currentUser } from './session';
export async function requireDepartmentManage() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (
    !user.contextId ||
    user.contextId === 'platform' ||
    !user.permissions.includes('org.departments.manage')
  )
    redirect('/home');
  return user;
}
