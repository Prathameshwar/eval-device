import type { ReactNode } from 'react';
import { Notice } from '@pms/ui';
import { DeviceDirectoryProvider } from '@/components/DeviceDirectoryProvider';
import { deviceOptions } from '@/lib/device-actions';
import { consoleError } from '@/lib/console-errors';
import { requireDeviceRead } from '@/lib/device-access';
export default async function DeviceLayout({ children }: { children: ReactNode }) {
  const user = await requireDeviceRead();
  try {
    const options = await deviceOptions(user.contextId!);
    return <DeviceDirectoryProvider key={options.contextId} {...options}>{children}</DeviceDirectoryProvider>;
  } catch (error) {
    return <Notice tone="danger" title="Devices unavailable">{consoleError(error)} <a href="/devices">Retry</a></Notice>;
  }
}
