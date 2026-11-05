import type { Metadata } from 'next';
import { DeviceList } from '@/components/DeviceList';
import { requireDeviceRead } from '@/lib/device-access';

export const metadata: Metadata = { title: 'Devices' };

export default async function Page({ searchParams }: { searchParams: Promise<{ configureModel?: string }> }) {
  await requireDeviceRead();
  const params = await searchParams;
  return <DeviceList initialConfigureDevice={params.configureModel} />;
}
