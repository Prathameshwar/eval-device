import { Badge, type Tone } from '@pms/ui';
import { isDeviceOnline, type Device } from '@/lib/device-directory';

export const ENROLLMENT_STATUS: Record<Device['enrollment_state'], { label: string; tone: Tone }> = {
  pending: { label: 'Pending', tone: 'info' },
  enrolled: { label: 'Enrolled', tone: 'success' },
  retired: { label: 'Retired', tone: 'warn' },
};

export function DeviceStatusBadge({ device, nowString }: { device: Device; nowString?: string }) {
  const enrollment = ENROLLMENT_STATUS[device.enrollment_state];
  return <Badge tone={enrollment.tone}>{enrollment.label}</Badge>;
}

export function DeviceConnectionBadge({ device, nowString }: { device: Device; nowString?: string }) {
  const online = isDeviceOnline(device, nowString);
  return (
    <Badge tone={online ? 'success' : 'neutral'}>
      {online ? 'Online' : 'Offline'}
    </Badge>
  );
}
