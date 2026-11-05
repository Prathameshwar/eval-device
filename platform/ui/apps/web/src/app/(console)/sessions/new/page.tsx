import { redirect } from 'next/navigation';
import { requireHistory } from '@/lib/history-access';
import { canStartSession } from '@/lib/session-start';
import { StartSessionPage } from '@/components/StartSessionPage';

export default async function Page() {
  const user = await requireHistory();
  if (!canStartSession(user.permissions)) redirect('/sessions');
  return <StartSessionPage key={user.contextId} contextId={user.contextId!} />;
}
