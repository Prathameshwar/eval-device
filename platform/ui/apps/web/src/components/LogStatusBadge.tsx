import { Badge, type Tone } from '@pms/ui';
import type { ActivityEvent } from '@/lib/log-directory';

export const SEVERITY_TONES: Record<ActivityEvent['severity'], { label: string; tone: Tone }> = {
  info: { label: 'Info', tone: 'info' },
  warning: { label: 'Warning', tone: 'warn' },
  error: { label: 'Error', tone: 'danger' },
};

export function LogSeverityBadge({ severity }: { severity: ActivityEvent['severity'] }) {
  const presentation = SEVERITY_TONES[severity];
  return <Badge tone={presentation.tone}>{presentation.label}</Badge>;
}
