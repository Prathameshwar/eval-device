import type { Metadata } from 'next';
import { InvitationForm } from '@/components/InvitationForm';
import { currentUser } from '@/lib/session';
export const metadata: Metadata = { title: 'Accept invitation', robots: { index: false, follow: false }, referrer: 'no-referrer' };
export default async function Page() {
  const user = await currentUser();
  return <InvitationForm signedInEmail={user?.email} />;
}
