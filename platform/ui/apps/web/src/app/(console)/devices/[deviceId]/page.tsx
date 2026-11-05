import { BackNavigation } from '@/components/BackNavigation';
import type { Metadata } from 'next';
import { Notice } from '@pms/ui';
import { readDevice } from '@/lib/device-actions';
import { DeviceDetails } from '@/components/DeviceDetails';
import { requireDeviceRead } from '@/lib/device-access';

export const metadata: Metadata = { title: 'Device details' };

export default async function Page({ params }: { params: Promise<{ deviceId: string }> }) {
  const user = await requireDeviceRead();
  const { deviceId } = await params;
  const result = await readDevice(user.contextId!, deviceId);
  if (result.error !== undefined) return <div className="pms-page"><BackNavigation href="/devices" label="Back to devices" /><Notice tone="danger" title="Device unavailable">{result.error}</Notice></div>;
  return <DeviceDetails key={user.contextId + deviceId} deviceId={deviceId} initialDevice={result.value} />;
}
