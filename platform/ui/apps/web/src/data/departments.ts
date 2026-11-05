import type { Department } from '@/lib/department-directory';

export const DEMO_DEPARTMENTS: readonly Department[] = [
  {
    id: '30000000-0000-4000-8000-000000000001',
    organization_id: '10000000-0000-4000-8000-000000000001',
    name: 'Cardiology',
    description: 'Deals with disorders of the heart and parts of the circulatory system.',
    is_active: true,
    status_reason: null,
    created_at: '2026-01-10T08:00:00.000Z',
    updated_at: '2026-01-10T08:00:00.000Z',
    archived_at: null,
    management_version: 1,
  },
  {
    id: '30000000-0000-4000-8000-000000000002',
    organization_id: '10000000-0000-4000-8000-000000000001',
    name: 'Respiratory',
    description: 'Specializes in the diagnosis and treatment of lung and chest infections.',
    is_active: true,
    status_reason: null,
    created_at: '2026-01-15T09:30:00.000Z',
    updated_at: '2026-01-15T09:30:00.000Z',
    archived_at: null,
    management_version: 1,
  },
  {
    id: '30000000-0000-4000-8000-000000000003',
    organization_id: '10000000-0000-4000-8000-000000000001',
    name: 'Nephrology',
    description: 'Deals with the physiology and diseases of the kidneys.',
    is_active: true,
    status_reason: null,
    created_at: '2026-02-01T10:15:00.000Z',
    updated_at: '2026-02-01T10:15:00.000Z',
    archived_at: null,
    management_version: 1,
  },
  {
    id: '30000000-0000-4000-8000-000000000004',
    organization_id: '10000000-0000-4000-8000-000000000001',
    name: 'Neurology',
    description: 'Specialized in treating disorders that affect the brain, spinal cord, and nerves.',
    is_active: false,
    status_reason: 'Temporary suspension during clinical restructure.',
    created_at: '2026-02-10T14:00:00.000Z',
    updated_at: '2026-08-20T11:00:00.000Z',
    archived_at: null,
    management_version: 2,
  },
  {
    id: '30000000-0000-4000-8000-000000000005',
    organization_id: '10000000-0000-4000-8000-000000000001',
    name: 'Pediatrics (Archived)',
    description: 'Medical care of infants, children, and adolescents.',
    is_active: false,
    status_reason: null,
    created_at: '2026-01-05T08:30:00.000Z',
    updated_at: '2026-09-01T09:00:00.000Z',
    archived_at: '2026-09-01T09:00:00.000Z',
    management_version: 2,
  }
];

export const DEPARTMENT_MAP: Record<string, string> = DEMO_DEPARTMENTS.reduce(
  (map, dept) => ({ ...map, [dept.id]: dept.name }),
  {} as Record<string, string>
);
