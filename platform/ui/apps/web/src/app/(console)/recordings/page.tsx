import { requireHistory } from '@/lib/history-access';
import { HistoryWorkspace } from '@/components/HistoryWorkspace';
export default async function Page() {
  const user = await requireHistory(true);
  return (
    <HistoryWorkspace
      key={user.contextId}
      contextId={user.contextId!}
      mode="recordings"
      canManage={user.permissions.includes('org.processing.execute')}
      canMedia={user.permissions.includes('org.media.read')}
    />
  );
}
