import { redirect } from 'next/navigation';
import { currentUser } from './session';

export async function requireDeviceRead() {
  const user = await currentUser();
  if (!user) redirect('/login');
  
  // Verify if the user has devices read permissions
  const hasAccess = user.permissions.includes('org.devices.summary.read') || 
                    user.permissions.includes('org.devices.read') ||
                    user.permissions.includes('platform.health.read');
                    
  if (!hasAccess || !user.contextId) redirect('/home');
  return user;
}
