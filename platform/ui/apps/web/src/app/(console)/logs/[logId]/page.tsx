import type { Metadata } from 'next';
import { LogDetails } from '@/components/LogDetails';
import { requireLogRead } from '@/lib/log-access';

export const metadata: Metadata = { title: 'Log details' };

export default async function Page({ params }: { params: Promise<{ logId: string }> }) {
  const user = await requireLogRead();
  const { logId } = await params;
  return <LogDetails key={user.contextId + logId} logId={logId} user={user} />;
}
