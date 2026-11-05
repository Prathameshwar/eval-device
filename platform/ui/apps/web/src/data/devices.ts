import type { Device } from '@/lib/device-directory';
import { DEPARTMENT_MAP } from './departments';

export const DEMO_DEPARTMENTS: Readonly<Record<string, string>> = DEPARTMENT_MAP;

const NAMES = [
  'SimStation', 'OPD Laptop', 'Lab Raspberry', 'ER Tablet', 'Ward Station', 'ICU Monitor', 'Clinic Desk'
];

export const DEMO_DEVICES: readonly Device[] = NAMES.flatMap((name, group) =>
  [1, 2, 3].map((index): Device => {
    const idx = group * 3 + index;
    const isEven = idx % 2 === 0;
    const isThree = idx % 3 === 0;

    // Stable historical dates
    const created = new Date(Date.UTC(2026, 4, 1 + idx)).toISOString();
    const registered = idx % 5 !== 0 ? new Date(Date.UTC(2026, 4, 2 + idx)).toISOString() : null;
    const enrolled = registered && idx % 7 !== 0 ? new Date(Date.UTC(2026, 4, 3 + idx)).toISOString() : null;

    // Simulate heartbeats. If idx % 4 === 0, device is currently online (last_seen_at is recent)
    // We hardcode some dates as well to prevent clock issues, but let's make some very recent relative to September 22, 2026.
    const isOnline = idx % 4 === 0;
    const lastSeen = enrolled
      ? isOnline
        ? '2026-09-22T10:15:00.000Z'
        : new Date(Date.UTC(2026, 8, 10 + (idx % 12))).toISOString()
      : null;

    const deviceType = isEven ? 'laptop' : isThree ? 'raspberry_pi' : 'other';
    // A device row always exists as 'pending' from creation (there is no separate "unregistered" state);
    // it becomes 'enrolled' once the agent redeems an enrollment token, or 'retired' afterwards.
    const enrollmentState = !enrolled ? 'pending' : idx % 10 === 0 ? 'retired' : 'enrolled';

    const deptKeys = Object.keys(DEMO_DEPARTMENTS);

    return {
      id: `50000000-0000-4000-8000-${String(idx).padStart(12, '0')}`,
      device_unique_id: `DEVICE-${String(idx).padStart(4, '0')}`,
      organization_id: '10000000-0000-4000-8000-000000000001', // Northside Medical College
      department_id: idx % 4 !== 0 ? deptKeys[idx % deptKeys.length]! : null,
      name: `${name} ${String(index).padStart(2, '0')}`,
      description: `Fictional ${deviceType} simulation device placed in the main facility.`,
      device_type: deviceType,
      is_active: enrollmentState === 'enrolled' && idx % 6 !== 0,
      enrollment_state: enrollmentState,
      created_at: created,
      registered_at: registered,
      enrolled_at: enrolled,
      last_seen_at: lastSeen,
      last_activity_at: lastSeen,
      location: `Floor ${2 + (idx % 4)}, Room ${101 + idx}`,
      contact_name: idx % 3 !== 0 ? 'Facilities Desk' : null,
      contact_email: idx % 3 !== 0 ? 'facilities@example.org' : null,
      contact_phone: null,
      management_version: 1,
    };
  })
);
