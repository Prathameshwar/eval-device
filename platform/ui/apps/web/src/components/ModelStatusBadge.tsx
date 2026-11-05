import { Badge, type Tone } from '@pms/ui';
import type { ModelDefinition } from '@/lib/model-directory';

export const LIFECYCLE_TONES: Record<ModelDefinition['lifecycle'], { label: string; tone: Tone }> = {
  active: { label: 'Active', tone: 'success' },
  deprecated: { label: 'Deprecated', tone: 'warn' },
  retired: { label: 'Retired', tone: 'neutral' },
};

export const ADAPTER_TONES: Record<ModelDefinition['adapter_status'], { label: string; tone: Tone }> = {
  available: { label: 'Adapter Active', tone: 'info' },
  unavailable: { label: 'No Adapter', tone: 'neutral' },
};

export function ModelLifecycleBadge({ lifecycle }: { lifecycle: ModelDefinition['lifecycle'] }) {
  const presentation = LIFECYCLE_TONES[lifecycle];
  return <Badge tone={presentation.tone}>{presentation.label}</Badge>;
}

export function ModelAdapterBadge({ adapterStatus }: { adapterStatus: ModelDefinition['adapter_status'] }) {
  const presentation = ADAPTER_TONES[adapterStatus];
  return <Badge tone={presentation.tone}>{presentation.label}</Badge>;
}
