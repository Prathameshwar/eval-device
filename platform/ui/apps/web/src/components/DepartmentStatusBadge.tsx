import { Badge, type Tone } from '@pms/ui';
import { departmentStatus, type Department } from '@/lib/department-directory';

export const DEPARTMENT_STATUS_TONES: Record<'active' | 'inactive' | 'archived', { label: string; tone: Tone }> = {
  active: { label: 'Active', tone: 'success' },
  inactive: { label: 'Inactive', tone: 'neutral' },
  archived: { label: 'Archived', tone: 'warn' },
};

export function DepartmentStatusBadge({ department }: { department: Department }) {
  const status = departmentStatus(department);
  const presentation = DEPARTMENT_STATUS_TONES[status];
  return <Badge tone={presentation.tone}>{presentation.label}</Badge>;
}
