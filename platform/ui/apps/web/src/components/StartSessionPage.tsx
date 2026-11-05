'use client';

import { SessionQueueWorkspace } from './SessionQueueWorkspace';

export function StartSessionPage({ contextId }: { contextId: string }) {
  return <SessionQueueWorkspace contextId={contextId} initialPlan />;
}
