export type Device = {
  id: string;
  device_unique_id: string;
  organization_id: string;
  department_id: string | null;
  name: string;
  description: string | null;
  device_type: 'manikin' | 'laptop' | 'raspberry_pi' | 'other';
  is_active: boolean;
  enrollment_state: 'pending' | 'enrolled' | 'retired';
  created_at: string;
  registered_at: string | null;
  enrolled_at: string | null;
  last_seen_at: string | null;
  last_activity_at: string | null;
  location: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  management_version?: number;
  management_etag?: string;
  updated_at?: string;
  connectivity?: 'online' | 'offline';
  credential_status?: 'active' | 'revoked' | 'not_issued';
  preferred_language?: string | null;
  summary_only?: boolean;
  models_configured?: boolean;
  organization_name?: string;
  department_name?: string;
};

export type DeviceQuery = {
  q: string;
  organization_id?: string;
  exclude_organization_id?: string;
  is_active: boolean | undefined;
  device_type: 'manikin' | 'laptop' | 'raspberry_pi' | 'other' | undefined;
  enrollment_state: 'pending' | 'enrolled' | 'retired' | 'current' | undefined;
  department_id: string | undefined;
  online: boolean | undefined;
  sort_by: 'name' | 'created_at' | 'last_seen_at';
  sort_order: 'asc' | 'desc';
  limit: number;
};

export const DEVICE_PAGE_LIMITS = [25, 50, 100] as const;
export const DEVICE_TYPES = [
  { value: 'manikin', label: 'Manikin (Physical)' },
  { value: 'laptop', label: 'Laptop (Software)' },
] as const;
export function deviceTypeLabel(type: Device['device_type']): string {
  return DEVICE_TYPES.find(item => item.value === type)?.label ??
    (type === 'raspberry_pi' ? 'Legacy Raspberry Pi' : 'Legacy Other');
}

export const DEFAULT_DEVICE_QUERY: DeviceQuery = {
  q: '',
  is_active: undefined,
  device_type: undefined,
  enrollment_state: 'current',
  department_id: undefined,
  online: undefined,
  sort_by: 'name',
  sort_order: 'asc',
  limit: 25,
};

/**
 * Connectivity matches FastAPI behavior:
 * Live records use the server-computed connectivity and configured timeout.
 * Legacy fixtures may supply an explicit clock when no API value is available.
 */
export function isDeviceOnline(device: Device, nowString = new Date().toISOString()): boolean {
  if (device.connectivity) return device.connectivity === 'online';
  if (!device.last_seen_at) return false;
  const lastSeen = new Date(device.last_seen_at).getTime();
  const current = new Date(nowString).getTime();
  const offlineSeconds = 180;
  return current - lastSeen <= offlineSeconds * 1000;
}

/**
 * Filter, Sort, and Slice mock data locally.
 */
export function devicePage(
  rows: readonly Device[],
  query: DeviceQuery,
  requestedPage: number,
  nowString = '2026-09-22T10:15:00.000Z'
) {
  const needle = query.q.trim().slice(0, 128).toLowerCase();
  const direction = query.sort_order === 'asc' ? 1 : -1;
  const compare = (left: string | null, right: string | null) => {
    const l = left ?? '';
    const r = right ?? '';
    return l < r ? -1 : l > r ? 1 : 0;
  };

  const matches = rows.filter((row) => {
    const matchesQuery = !needle ||
      row.name.toLowerCase().includes(needle) ||
      row.device_unique_id.toLowerCase().includes(needle) ||
      (row.location && row.location.toLowerCase().includes(needle)) ||
      row.id.toLowerCase().includes(needle);

    const matchesActive = query.is_active === undefined || row.is_active === query.is_active;
    const matchesType = query.device_type === undefined || row.device_type === query.device_type;
    const matchesEnrollment = query.enrollment_state === undefined || (query.enrollment_state === 'current' ? row.enrollment_state !== 'retired' : row.enrollment_state === query.enrollment_state);
    const matchesDepartment = query.department_id === undefined || row.department_id === query.department_id;
    const matchesOnline = query.online === undefined || isDeviceOnline(row, nowString) === query.online;

    return matchesQuery && matchesActive && matchesType && matchesEnrollment && matchesDepartment && matchesOnline;
  }).sort((left, right) => {
    const primaryCompare = compare(left[query.sort_by], right[query.sort_by]);
    return direction * (primaryCompare || compare(left.id, right.id));
  });

  const limit = Math.max(1, Math.min(100, query.limit));
  const page = Math.max(0, Math.min(requestedPage, Math.ceil(matches.length / limit) - 1));
  const offset = page * limit;

  return {
    items: matches.slice(offset, offset + limit),
    total: matches.length,
    page,
    from: matches.length ? offset + 1 : 0,
    has_more: offset + limit < matches.length,
  };
}

export function retireDevice(device: Device, timestamp: string): Device {
  if (device.enrollment_state === 'retired') return device;
  return {
    ...device,
    is_active: false,
    enrollment_state: 'retired',
    last_activity_at: timestamp,
    management_version: (device.management_version ?? 0) + 1,
  };
}
