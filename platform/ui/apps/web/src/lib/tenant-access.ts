import { redirect } from 'next/navigation';
import { currentUser } from './session';
export async function requireTenantRead() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!user.permissions.includes('platform.organizations.read')) redirect('/home');
}
