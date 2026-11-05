import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { loadHome } from '@/lib/home-api';
import { consoleError } from '@/lib/console-errors';
import { ApiError } from '@/lib/api';
import { Dashboard, TenantClinicalHome } from '@/components/dashboards';
import { currentUser } from '@/lib/session';
import { Notice } from '@pms/ui';

export const metadata: Metadata = {
  title: 'Home',
  description: 'Your AI Evaluator dashboard.',
};

/**
 * The console's home. The layout has already refused anyone without a session; this reads the
 * user again rather than threading it down, because a layout cannot pass props to a page in the
 * App Router and a context for one value would be worse than a second cookie read.
 */
export default async function HomePage() {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (user.needsAccess) return <Notice tone="info" title="Your account is ready">Ask your administrator to assign you to an active organisation. You can manage your password or sign out from the account menu.</Notice>;
  if (user.role === 'org_admin') return <TenantClinicalHome user={user} />;

  try {
    return <Dashboard user={user} data={await loadHome(user)} />;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect('/login');
    return <Notice tone="danger" title="Dashboard unavailable">{consoleError(error)} <a href="/home">Reload dashboard</a></Notice>;
  }
}
