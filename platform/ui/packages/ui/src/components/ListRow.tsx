import type { ReactNode } from 'react';
import type { Tone } from './Badge';
import { isSafeHref } from '../lib/url';
import { ExternalLinkIcon } from './icons-console';
import { Meter } from './Meter';

type ListRowProps = {
  /** A ranked list's position. Takes the lead slot; `icon` fills it otherwise. */
  rank?: number;
  /** A status glyph for an unranked row — pair it with a tone, never colour alone. */
  icon?: ReactNode;
  primary: ReactNode;
  /** The muted, tabular second line: dates, counts, references. */
  meta?: ReactNode;
  /** Already-formatted figure, right-aligned and tabular. A string, never a number. */
  figure?: ReactNode;
  /** 0–1. Renders a `Meter` with the percentage as a trailing label. */
  share?: number;
  /**
   * Only `https:`, `http:`, a site-relative path, a fragment or `mailto:` is linked. Anything
   * else renders as plain text — see `isSafeHref`.
   */
  href?: string;
  /** Opens in a new tab, marked with an icon and announced as such. */
  external?: boolean;
  /**
   * Tones the leading icon and the share meter. Defaults to `neutral` so the colour can never
   * contradict the glyph: a `WarnTriangleIcon` with no tone must not come out brand indigo.
   */
  tone?: Tone;
};

export function ListRow({
  rank,
  icon,
  primary,
  meta,
  figure,
  share,
  href,
  external = false,
  tone = 'neutral',
}: ListRowProps) {
  const externalProps = external ? { target: '_blank', rel: 'noopener noreferrer' } : {};
  // A rejected href degrades to plain text rather than to a dead anchor: an anchor with no
  // destination is still a tab stop announced as a link.
  const linkHref = href !== undefined && isSafeHref(href) ? href : undefined;

  return (
    <div className="pms-list-row" data-tone={tone}>
      {rank != null ? (
        <span className="pms-list-row__rank pms-figure">{rank}</span>
      ) : icon ? (
        <span className="pms-list-row__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}

      <div className="pms-list-row__main">
        <div className="pms-list-row__top">
          {linkHref ? (
            <a className="pms-list-row__primary pms-link" href={linkHref} {...externalProps}>
              {primary}
              {external ? (
                <>
                  <ExternalLinkIcon size={13} />
                  <span className="pms-visually-hidden"> (opens in a new tab)</span>
                </>
              ) : null}
            </a>
          ) : (
            <span className="pms-list-row__primary">{primary}</span>
          )}
          {figure ? <span className="pms-list-row__figure pms-figure">{figure}</span> : null}
        </div>
        {meta ? <p className="pms-meta">{meta}</p> : null}
        {share != null ? (
          <Meter
            value={share}
            tone={tone}
            /* Name the meter after its row: a page of meters all called "Share" is unusable
             * to anyone navigating by control. */
            label={typeof primary === 'string' ? `Share — ${primary}` : 'Share'}
          />
        ) : null}
      </div>
    </div>
  );
}
