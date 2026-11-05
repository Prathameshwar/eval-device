import { redirect } from 'next/navigation';
import { requireSettingsSection } from '@/lib/settings-access';

export default async function Page({ searchParams }: { searchParams: Promise<{ device?: string; tenant?: string }> }) {
  await requireSettingsSection('models');
  const params = await searchParams;
  redirect(params.device ? '/devices?configureModel=' + encodeURIComponent(params.device) : '/devices');
}
