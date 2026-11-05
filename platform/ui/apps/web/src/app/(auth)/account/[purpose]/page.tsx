import { notFound } from 'next/navigation';
import { AccountActionForm, type AccountPurpose } from '@/components/AccountActionForm';

export const metadata = { title: 'Update account' };

export default async function AccountPage({ params }: { params: Promise<{ purpose: string }> }) {
  const { purpose } = await params;
  if (!['setup', 'password-reset', 'email-change'].includes(purpose)) notFound();
  return <AccountActionForm key={purpose} purpose={purpose as AccountPurpose} />;
}
