import type { ReactNode } from 'react';
import type { Tone } from './Badge';

type CardProps = {
  children: ReactNode;
  /** Tints the whole card with a signal triplet — for a card that *is* a warning. */
  tone?: Tone;
  /** A card sitting inside another card: `--pms-surface-2`, so the nesting reads. */
  nested?: boolean;
  className?: string;
};

/** White surface, 6px ledger radius, one hairline, almost no shadow. */
export function Card({ children, tone, nested = false, className = '' }: CardProps) {
  const classes = ['pms-card', nested ? 'pms-card--nested' : '', className]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} data-tone={tone}>
      {children}
    </div>
  );
}

type CardHeaderProps = {
  icon?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  /** A count or status pill, on the title's baseline. */
  badge?: ReactNode;
  /** An interactive affordance — a link, an `IconButton`, a `Select`. */
  action?: ReactNode;
};

/**
 * The title is an `<h3>`: a card sits inside a `SectionHeader`'s `<h2>`, which sits under the
 * page's `<h1>`, so the outline descends without a skipped level.
 */
export function CardHeader({ icon, title, subtitle, badge, action }: CardHeaderProps) {
  return (
    <div className="pms-card__header">
      <div className="pms-card__heading">
        {icon ? (
          <span className="pms-card__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <div className="pms-card__titles">
          <h3 className="pms-card__title">{title}</h3>
          {subtitle ? <p className="pms-card__subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {badge || action ? (
        <div className="pms-card__aside">
          {badge}
          {action}
        </div>
      ) : null}
    </div>
  );
}

export function CardBody({ children }: { children: ReactNode }) {
  return <div className="pms-card__body">{children}</div>;
}

export function CardFooter({ children }: { children: ReactNode }) {
  return <div className="pms-card__footer">{children}</div>;
}
