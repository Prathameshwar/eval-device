import { redirect } from 'next/navigation';
import { currentUser } from './session';
import { canOpenSettingsRoute, type SettingsId } from './settings';

/** Check direct routes independently from the cards shown on the Settings page. */
export async function requireSettingsSection(id: SettingsId) {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!canOpenSettingsRoute(user.role, id, permission => user.permissions.includes(permission))) redirect('/home');
  return user;
}
