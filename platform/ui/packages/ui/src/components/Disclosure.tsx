'use client';

import { useState, type ReactNode } from 'react';
import { ChevronRightIcon } from './icons-console';

type DisclosureProps = {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
};

/**
 * Native `<details>`/`<summary>`: Enter/Space, the AT "expanded" state and the disclosure
 * semantics all come free, and no ARIA can be got wrong. State is mirrored from the element's
 * own `toggle` event rather than driven, so a parent re-render can't slam an open panel shut.
 */
export function Disclosure({ summary, children, defaultOpen = false }: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <details
      className="pms-disclosure"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="pms-disclosure__summary">
        <span className="pms-disclosure__caret" aria-hidden="true">
          <ChevronRightIcon size={14} />
        </span>
        <span className="pms-disclosure__label">{summary}</span>
      </summary>
      <div className="pms-disclosure__body">{children}</div>
    </details>
  );
}
