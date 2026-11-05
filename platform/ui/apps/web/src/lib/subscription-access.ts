import { redirect } from 'next/navigation';
import { currentUser } from './session';
export async function requireSubscriptionRead() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!user.contextId || !user.permissions.includes(user.contextId === 'platform' ? 'platform.organizations.read' : 'org.settings.read')) redirect('/home');
  return user;
}
