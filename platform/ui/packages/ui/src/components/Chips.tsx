import type { ReactNode } from 'react';

import { ShieldIcon } from './icons';

/** Each tone maps to a `--pms-<tone>-{ink,tint,line}` triplet — never a lone colour. */
export type ChipTone = 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info';

/**
 * What the dot means, in words. The dot itself is decorative, so without this the tone
 * would be conveyed by colour alone — which fails the accessibility floor (§7) and is
 * invisible to anyone reading the page through a screen reader or a greyscale display.
 */
const TONE_DESCRIPTION: Record<ChipTone, string> = {
  neutral: 'no status',
  brand: 'active',
  success: 'healthy',
  warn: 'needs attention',
  danger: 'critical',
  info: 'for information',
};

/**
 * The top bar's "where am I" pill: the current company, fiscal year or environment.
 * Read-only — it states context, it does not switch it (that is `OrgSwitcher`).
 */
export function ContextChip({ label, tone = 'neutral' }: { label: string; tone?: ChipTone }) {
  return (
    <span className="pms-chip" data-tone={tone}>
      <span className="pms-chip__dot" aria-hidden="true" />
      <span className="pms-chip__label">{label}</span>
      <span className="pms-visually-hidden">{` (${TONE_DESCRIPTION[tone]})`}</span>
    </span>
  );
}

/**
 * The actor's role. A shield by default because a role is an authority claim; a caller
 * with a better glyph for a specific role passes one.
 */
export function RoleChip({ label, icon }: { label: string; icon?: ReactNode }) {
  return (
    <span className="pms-chip pms-chip--role" data-tone="neutral">
      <span className="pms-chip__icon" aria-hidden="true">
        {icon ?? <ShieldIcon size={14} />}
      </span>
      <span className="pms-chip__label">{label}</span>
    </span>
  );
}
