import type { Metadata } from 'next';
import { Subscriptions, SubscriptionDetails } from '@/components/Subscriptions';
import { requireSubscriptionRead } from '@/lib/subscription-access';
export const metadata: Metadata = { title: 'Subscriptions' };
export default async function Page() {
  const user = await requireSubscriptionRead();
  return user.contextId === 'platform'
    ? <Subscriptions key={user.contextId} contextId={user.contextId} />
    : <SubscriptionDetails key={user.contextId} contextId={user.contextId!} organizationId={user.contextId!} />;
}
