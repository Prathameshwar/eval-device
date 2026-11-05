import { requireHistory } from '@/lib/history-access';
import { HistoryWorkspace } from '@/components/HistoryWorkspace';
import { canStartSession } from '@/lib/session-start';
export default async function Page() {
  const user = await requireHistory(false);
  return (
    <HistoryWorkspace
      key={user.contextId}
      contextId={user.contextId!}
      viewerId={user.id}
      mode="reports"
      canManage={canStartSession(user.permissions)}
      canMedia={user.permissions.includes('org.media.read')}
    />
  );
}
