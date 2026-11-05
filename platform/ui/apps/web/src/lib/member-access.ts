import { redirect } from 'next/navigation';
import { currentUser } from './session';

export async function requireMemberManage() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!user.contextId || user.contextId === 'platform' || !user.permissions.includes('org.members.manage')) redirect('/home');
  return user;
}
