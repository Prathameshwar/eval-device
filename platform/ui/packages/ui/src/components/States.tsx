import type { ReactNode } from 'react';
import { InfoIcon, WarnTriangleIcon, XCircleIcon } from './icons-console';

type EmptyStateProps = {
  icon?: ReactNode;
  title: ReactNode;
  body?: ReactNode;
  /** The way out — "Create the first invoice", "Clear filters". */
  action?: ReactNode;
};

export function EmptyState({ icon, title, body, action }: EmptyStateProps) {
  return (
    <div className="pms-state">
      {icon ? (
        <span className="pms-state__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <p className="pms-state__title">{title}</p>
      {body ? <p className="pms-state__body">{body}</p> : null}
      {action ? <div className="pms-state__action">{action}</div> : null}
    </div>
  );
}

export type ErrorStatus = 401 | 403 | 422 | 500;

/**
 * One intended message per failure the API can hand a screen. A 401 and a 403 are different instructions to the reader: sign in again,
 * versus ask someone for access. Falling back to one generic string is how a real permission
 * problem gets read as an outage.
 */
const ERROR_COPY: Record<ErrorStatus, { title: string; body: string; icon: ReactNode }> = {
  401: {
    title: 'Your session has ended',
    body: 'Sign in again to continue where you left off.',
    icon: <InfoIcon size={20} />,
  },
  403: {
    title: "You don't have access to this",
    body: 'Your role does not include this data. Ask an administrator if you need it.',
    icon: <XCircleIcon size={20} />,
  },
  422: {
    title: "We couldn't accept those details",
    body: 'Some values were rejected. Check the highlighted fields and try again.',
    icon: <WarnTriangleIcon size={20} />,
  },
  500: {
    title: 'Something went wrong',
    body: 'The request failed on our side. Nothing was changed — try again in a moment.',
    icon: <WarnTriangleIcon size={20} />,
  },
};

type ErrorStateProps = {
  status: ErrorStatus;
  /** Server-supplied detail, shown *beside* the intended copy — never instead of it. */
  detail?: ReactNode;
  action?: ReactNode;
};

export function ErrorState({ status, detail, action }: ErrorStateProps) {
  const copy = ERROR_COPY[status];

  return (
    <div className="pms-state pms-state--error" data-tone="danger" role="alert">
      {/* The icon is what keeps this from being a colour-only signal. */}
      <span className="pms-state__icon" aria-hidden="true">
        {copy.icon}
      </span>
      <p className="pms-state__title">{copy.title}</p>
      <p className="pms-state__body">{copy.body}</p>
      {detail ? <p className="pms-state__detail pms-fine">{detail}</p> : null}
      {action ? <div className="pms-state__action">{action}</div> : null}
    </div>
  );
}

type SkeletonProps = {
  lines?: number;
  /** Any CSS length — the placeholder's width isn't something a token can know. */
  width?: string;
};

/**
 * Loading placeholder. `aria-hidden` on purpose: a screen reader should hear the loaded
 * content or a live region, never a description of grey bars.
 */
export function Skeleton({ lines = 3, width }: SkeletonProps) {
  // Clamped once, so the attribute and the rendered bars can't disagree.
  const count = Math.max(1, lines);

  return (
    <div
      className="pms-skeleton"
      aria-hidden="true"
      style={width ? { width } : undefined}
      data-lines={count}
    >
      {Array.from({ length: count }, (_, index) => (
        <span key={index} className="pms-skeleton__line" />
      ))}
    </div>
  );
}
