import 'server-only';
import { redirect } from 'next/navigation';
import { currentUser } from './session';
export async function requireHistory(media = false) {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (
    !user.contextId ||
    user.contextId === 'platform' ||
    !user.permissions.includes('org.results.read') ||
    (media && !user.permissions.includes('org.media.read'))
  )
    redirect('/home');
  return user;
}
