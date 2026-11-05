import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { SubscriptionDetails } from '@/components/Subscriptions';
import { requireSubscriptionRead } from '@/lib/subscription-access';
export const metadata: Metadata = { title: 'Tenant subscription' };
export default async function Page({ params }: { params: Promise<{ organizationId: string }> }) {
  const user = await requireSubscriptionRead(); const { organizationId } = await params;
  if (user.contextId !== 'platform' && user.contextId !== organizationId) redirect('/licenses');
  return <SubscriptionDetails key={user.contextId + ':' + organizationId} contextId={user.contextId!} organizationId={organizationId} />;
}
