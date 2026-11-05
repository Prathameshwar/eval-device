import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { requireSettingsSection } from '@/lib/settings-access';

export const metadata: Metadata = { title: 'Models' };
export default async function Page() {
  await requireSettingsSection('models');
  redirect('/models');
}
