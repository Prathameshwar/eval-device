import type { ReactNode } from 'react';

export type StatTone = 'default' | 'brand' | 'success' | 'warn' | 'danger';

type StatTileProps = {
  label: ReactNode;
  /**
   * Already formatted, and a **string**: money and quantities never become a JS `number` on
   * the client. `null`, `undefined` or blank means *no data*, which is a
   * different fact from zero — it renders an em-dash, never `0`.
   */
  value: string | null | undefined;
  footnote?: ReactNode;
  icon?: ReactNode;
  /** Colours the figure with `--pms-<tone>-ink`. */
  tone?: StatTone;
  /** Additionally tints the tile with the tone's triplet — how a row marks its lead metric. */
  emphasis?: boolean;
  /** A tile inside a card: quieter surface and the smaller figure step. */
  nested?: boolean;
};

export function StatTile({
  label,
  value,
  footnote,
  icon,
  tone = 'default',
  emphasis = false,
  nested = false,
}: StatTileProps) {
  const classes = [
    'pms-stat',
    nested ? 'pms-stat--nested' : '',
    emphasis ? 'pms-stat--emphasis' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const hasValue = typeof value === 'string' && value.trim() !== '';

  return (
    <div className={classes} data-tone={tone}>
      <div className="pms-stat__label">
        {icon ? (
          <span className="pms-stat__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <span className="pms-stat__label-text">{label}</span>
      </div>
      <p className="pms-stat__value pms-figure">
        {hasValue ? (
          value
        ) : (
          /* An em-dash alone is announced as punctuation or skipped, so it carries a text
           * equivalent — "no value" and "0" must never sound the same either. */
          <>
            <span aria-hidden="true">&mdash;</span>
            <span className="pms-visually-hidden">No value</span>
          </>
        )}
      </p>
      {footnote ? <p className="pms-stat__footnote">{footnote}</p> : null}
    </div>
  );
}

type StatRowProps = {
  /** 4-up by default; 3-up for a three-metric band. Both collapse at 1100px and 680px. */
  columns?: 3 | 4;
  children: ReactNode;
};

export function StatRow({ columns = 4, children }: StatRowProps) {
  return (
    <div className="pms-stat-row" data-columns={columns}>
      {children}
    </div>
  );
}
