import type { Tenant } from '@/lib/tenant-directory';

/** Fictional subscription catalogue; labels are looked up, not invented fields on the API row. */
export const TENANT_PLANS: Readonly<Record<string, string>> = {
  '20000000-0000-4000-8000-000000000001': 'Standard',
  '20000000-0000-4000-8000-000000000002': 'Advanced',
};

const NAMES = [
  'Apex', 'Birchwood', 'Cedar', 'Eastbridge', 'Evergreen', 'Fairview', 'Harbour',
  'Hillcrest', 'Lakeside', 'Maple', 'Northside', 'Oakridge', 'Riverside',
  'Southbank', 'Stonebridge', 'Westhaven', 'Willow',
];
const TYPES = ['Medical College', 'Simulation Centre', 'Training Institute', 'Academy'];
const CONTACTS = ['Anita Rao', 'Ravi Shah', 'Meera Nair', 'Arjun Das', 'Sara Ali', 'Dev Patel'];

/** Stable dates/UUIDs prevent hydration drift. No real tenant or contact records are used. */
export const DEMO_TENANTS: readonly Tenant[] = NAMES.flatMap((name, group) =>
  TYPES.map((type, variant): Tenant => {
    const index = group * TYPES.length + variant;
    const created = new Date(Date.UTC(2026, 5, 1 + index)).toISOString();
    const updated = new Date(Date.UTC(2026, 7, 1 + index % 28)).toISOString();
    const archived = index % 11 === 10;
    const missingContact = index % 9 === 8;
    return {
      id: `10000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      name: index === 32 ? 'Lakeside Institute for Clinical Simulation and Continuing Education' : `${name} ${type}`,
      description: `Fictional ${name} tenant for clinical skills training and simulation.`,
      contact_name: missingContact ? null : CONTACTS[index % CONTACTS.length] ?? null,
      contact_email: missingContact ? null : `training.${index + 1}@example.com`,
      contact_phone: null,
      subscription_plan_id: `20000000-0000-4000-8000-00000000000${index % 3 === 0 ? 2 : 1}`,
      is_active: !archived && index % 4 !== 1,
      archived_at: archived ? '2026-09-01T09:00:00.000Z' : null,
      created_at: created,
      updated_at: updated,
      management_version: 1,
    };
  }),
);
