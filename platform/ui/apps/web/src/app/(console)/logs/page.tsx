import type { Metadata } from 'next';
import { LogList } from '@/components/LogList';
import { requireLogRead } from '@/lib/log-access';

export const metadata: Metadata = { title: 'Activity logs' };

export default async function Page() {
  await requireLogRead();
  return <LogList />;
}
