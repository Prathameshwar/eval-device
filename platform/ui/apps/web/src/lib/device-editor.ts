import { isEmailLike, normalizeEmail } from '@pms/ui';
import type { Device } from './device-directory';

export type DeviceDraft = {
  device_unique_id: string;
  organization_id: string;
  name: string;
  preferred_language: string;
  description: string;
  device_type: Device['device_type'];
  department_id: string;
  location: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  is_active: boolean;
  enrollment_state: 'pending' | 'enrolled' | 'retired';
};

export type DeviceField = Exclude<keyof DeviceDraft, 'is_active'>;
export type DeviceErrors = Partial<Record<DeviceField, string>>;

export const DEVICE_FIELD_LIMITS = {
  device_unique_id: 50,
  name: 256,
  description: 4000,
  location: 512,
  contact_name: 256,
  contact_email: 320,
  contact_phone: 80,
} as const;

export function deviceDraft(device: Device | null): DeviceDraft {
  return {
    device_unique_id: device?.device_unique_id ?? '',
    organization_id: device?.organization_id ?? '',
    name: device?.name ?? '',
    preferred_language: device?.preferred_language ?? '',
    description: device?.description ?? '',
    device_type: device?.device_type ?? 'laptop',
    department_id: device?.department_id ?? '',
    location: device?.location ?? '',
    contact_name: device?.contact_name ?? '',
    contact_email: device?.contact_email ?? '',
    contact_phone: device?.contact_phone ?? '',
    is_active: device?.is_active ?? true,
    enrollment_state: device?.enrollment_state ?? 'pending',
  };
}

export function validateDeviceDraft(
  draft: DeviceDraft,
  departments: Readonly<Record<string, string>>,
  creating: boolean,
  original?: Device | null
): DeviceErrors {
  const errors: DeviceErrors = {};
  if (creating && !draft.device_unique_id.trim()) errors.device_unique_id = 'Enter a device unique ID.';

  if (!draft.name.trim()) {
    errors.name = 'Enter a device name.';
  }

  for (const field of Object.keys(DEVICE_FIELD_LIMITS) as (keyof typeof DEVICE_FIELD_LIMITS)[]) {
    if (draft[field].trim().length > DEVICE_FIELD_LIMITS[field]) {
      errors[field] = `Use ${DEVICE_FIELD_LIMITS[field]} characters or fewer.`;
    }
  }

  if (creating && !['manikin', 'laptop'].includes(draft.device_type)) {
    errors.device_type = 'Choose an available device type.';
  }

  if (draft.department_id && !Object.prototype.hasOwnProperty.call(departments, draft.department_id) && (creating || draft.department_id !== original?.department_id || (!original?.is_active && draft.is_active))) {
    errors.department_id = 'Select an active department.';
  }

  const email = normalizeEmail(draft.contact_email);
  if (email && !isEmailLike(email)) {
    errors.contact_email = 'Enter an email address such as name@example.com.';
  }

  return errors;
}

export function saveDeviceDraft(
  draft: DeviceDraft,
  device: Device | null,
  id: string,
  timestamp: string
): Device {
  const optional = (value: string) => value.trim() || null;
  return {
    id: device?.id ?? id,
    device_unique_id: device?.device_unique_id ?? draft.device_unique_id.trim(),
    organization_id: device?.organization_id ?? '10000000-0000-4000-8000-000000000001',
    department_id: optional(draft.department_id),
    name: draft.name.trim(),
    description: optional(draft.description),
    device_type: device?.device_type ?? draft.device_type,
    // When editing, status can be configured; creation of new devices starts active if specified (following FastAPI defaults), or inactive.
    is_active: device ? draft.is_active : draft.is_active,
    enrollment_state: device?.enrollment_state ?? draft.enrollment_state,
    created_at: device?.created_at ?? timestamp,
    // The API always reports registered_at as the device's creation time; there is no separate registration step.
    registered_at: device?.registered_at ?? timestamp,
    enrolled_at: device?.enrolled_at ?? (draft.enrollment_state === 'enrolled' ? timestamp : null),
    last_seen_at: device?.last_seen_at ?? (draft.enrollment_state === 'enrolled' ? timestamp : null),
    last_activity_at: device?.last_activity_at ?? (draft.enrollment_state === 'enrolled' ? timestamp : null),
    location: optional(draft.location),
    contact_name: optional(draft.contact_name),
    contact_email: optional(normalizeEmail(draft.contact_email)),
    contact_phone: optional(draft.contact_phone),
    management_version: (device?.management_version ?? 0) + 1,
  };
}
