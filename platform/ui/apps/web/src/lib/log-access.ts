import { redirect } from 'next/navigation';
import { currentUser } from './session';
import { logCategories } from './log-directory';

export async function requireLogRead() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!logCategories(user).length) redirect('/home');
  return user;
}
