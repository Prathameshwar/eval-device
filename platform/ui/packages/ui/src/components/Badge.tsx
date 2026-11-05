import type { ReactNode } from 'react';

/**
 * The signal tones. Each name resolves to a `--pms-<tone>-{ink,tint,line}` triplet, and the
 * triplet is always used whole — coloured text on a plain surface is not a status. Declared here because `Badge` is the smallest thing that *is* a
 * triplet; `Card`, `Meter` and `ListRow` share the type rather than restating the union.
 */
export type Tone = 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info';

type BadgeProps = {
  children: ReactNode;
  tone?: Tone;
  /**
   * `tint` is the signal triplet · `outline` is the quiet hairline form · `mono` sets the
   * mono stack for codes (`INR`, `GSTIN`) where character width carries meaning.
   */
  variant?: 'tint' | 'outline' | 'mono';
};

export function Badge({ children, tone = 'neutral', variant = 'tint' }: BadgeProps) {
  return (
    <span className={`pms-badge pms-badge--${variant}`} data-tone={tone}>
      {children}
    </span>
  );
}
