import { requireHistory } from '@/lib/history-access';
import { SessionQueueWorkspace } from '@/components/SessionQueueWorkspace';
import { canStartSession } from '@/lib/session-start';
export default async function Page() {
  const user = await requireHistory(false);
  return (
    <SessionQueueWorkspace
      key={user.contextId}
      contextId={user.contextId!}
      canManage={canStartSession(user.permissions)}
    />
  );
}
