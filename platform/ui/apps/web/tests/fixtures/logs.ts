import type { ActivityEvent } from '../../src/lib/log-directory';
import { DEMO_USERS } from './accounts';
export const tenantId = '12345678-1234-4234-8234-123456789012';
export const logUser = { ...DEMO_USERS[2]!, contextId: tenantId };
export const logRecord: ActivityEvent = {
  id: '22345678-1234-4234-8234-123456789012', organization_id: tenantId, department_id: null, device_id: null,
  actor_type: 'system', actor_user_id: null, category: 'operational', event_type: 'device.status', severity: 'warning',
  entity_type: 'device', entity_id: null, run_id: null, source_event_id: null,
  occurred_at: '2026-09-24T10:00:00Z', received_at: '2026-09-24T10:00:01Z', expires_at: '2026-10-24T10:00:00Z',
  details: { status: 'ready' }, details_redacted: false,
};
export const logPage = { items: [logRecord], next_cursor: null, has_more: false, total: 1 };
