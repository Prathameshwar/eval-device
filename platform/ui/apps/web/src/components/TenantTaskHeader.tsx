'use client';

import { useEffect, useId, useRef } from 'react';
import { Button } from '@pms/ui';
import styles from './TenantAdministration.module.css';

export function TenantTaskHeader({ title, backLabel, onBack, steps, step, busy = false }: {
  title: string; backLabel: string; onBack: () => void; steps: string[]; step: number; busy?: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const progressId = useId();
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    // A long result list must not leave the next step scrolled halfway down.
    const body = heading.current?.closest('.pms-overlay-body');
    if (body) body.scrollTop = 0;
  }, [step]);
  return <header className={styles.taskHeader}>
    <Button variant="ghost" onClick={onBack} disabled={busy}>{backLabel}</Button>
    <div className={styles.taskTitle}><h3 ref={heading} tabIndex={-1} aria-describedby={progressId}>{title}</h3>
      <p id={progressId} className="pms-hint">Step {step + 1} of {steps.length} · {steps[step]}</p></div>
    <ol className={styles.steps} aria-label={`${title} steps`}>
      {steps.map((label, index) => <li key={label} aria-current={index === step ? 'step' : undefined} data-complete={index < step || undefined}>
        <span aria-hidden="true">{index + 1}</span>{label}
      </li>)}
    </ol>
  </header>;
}
