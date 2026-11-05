import type { ReactNode } from 'react';
import { requireSettingsSection } from '@/lib/settings-access';
export default async function ModelLayout({ children }: { children: ReactNode }) {
  await requireSettingsSection('models');
  return children;
}
