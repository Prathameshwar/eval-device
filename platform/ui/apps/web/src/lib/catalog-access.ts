import 'server-only';
import { redirect } from 'next/navigation';
import { currentUser } from './session';
export async function requireCatalog() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!user.contextId || user.contextId === 'platform' ||
      !user.permissions.some((p) => ['org.clinical.author', 'org.clinical.review', 'org.clinical.read'].includes(p)))
    redirect('/home');
  return user;
}
export async function requireScenario() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!user.contextId || user.contextId === 'platform' ||
      !user.permissions.some((p) => ['org.clinical.author', 'org.clinical.review'].includes(p)))
    redirect('/home');
  return user;
}
