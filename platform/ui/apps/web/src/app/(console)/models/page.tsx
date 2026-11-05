import type { Metadata } from 'next';
import { RuntimeModelsDirectory } from '@/components/RuntimeModelsDirectory';
import { requireSettingsSection } from '@/lib/settings-access';
export const metadata: Metadata = { title: 'Models' };
export default async function Page() {
  await requireSettingsSection('models');
  return <RuntimeModelsDirectory />;
}
