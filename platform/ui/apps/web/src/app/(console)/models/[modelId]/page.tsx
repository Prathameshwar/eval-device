import { redirect } from 'next/navigation';
import { requireSettingsSection } from '@/lib/settings-access';
export default async function Page({ params }: { params: Promise<{ modelId: string }> }) {
  await requireSettingsSection('models');
  await params;
  redirect('/models');
}
