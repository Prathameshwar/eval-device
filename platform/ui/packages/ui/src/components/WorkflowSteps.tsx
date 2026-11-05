type WorkflowStep = { id: string; label: string };

/** A compact progress list for page-based forms; navigation remains owned by the form. */
export function WorkflowSteps({ steps, current }: { steps: readonly WorkflowStep[]; current: string }) {
  const currentIndex = steps.findIndex((step) => step.id === current);
  return (
    <ol className="pms-workflow-steps" aria-label="Progress"
      style={{ '--pms-workflow-count': steps.length } as CSSProperties}>
      {steps.map((step, index) => (
        <li key={step.id} className="pms-workflow-steps__item"
          aria-current={step.id === current ? 'step' : undefined}
          data-complete={index < currentIndex ? 'true' : undefined}>
          <span className="pms-workflow-steps__number" aria-hidden="true">{index + 1}</span>
          <span>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}
import type { CSSProperties } from 'react';
