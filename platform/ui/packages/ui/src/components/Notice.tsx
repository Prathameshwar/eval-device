import type { ReactNode } from 'react';
import { IconButton } from './IconButton';
import {
  CheckCircleIcon,
  CloseIcon,
  InfoIcon,
  WarnTriangleIcon,
  XCircleIcon,
} from './icons-console';

export type NoticeTone = 'info' | 'success' | 'warning' | 'danger';

/**
 * The icon is what keeps a tone from being a colour-only signal. Exported and
 * shared with `Toast`, so a success is the same check whether it is stated inline or floated over
 * the page — two copies of this map is how the two surfaces drift into disagreeing.
 */
export const TONE_ICONS: Record<NoticeTone, ReactNode> = {
  info: <InfoIcon size={16} />,
  success: <CheckCircleIcon size={16} />,
  warning: <WarnTriangleIcon size={16} />,
  danger: <XCircleIcon size={16} />,
};

type NoticeProps = {
  tone?: NoticeTone;
  /** A short statement of what happened. The body says what to do about it. */
  title?: ReactNode;
  children: ReactNode;
  /** The way forward — "Start again", "Reload the list". */
  action?: ReactNode;
  /** Omit to render a notice the reader cannot dismiss — one stating a live constraint. */
  onDismiss?: () => void;
  /**
   * How it reaches a screen reader. `assertive` interrupts, and is the right answer for something
   * that just invalidated what the reader was doing — a rejected page cursor, a lost session.
   * `polite` waits its turn. `off` is for a notice that was on screen before they arrived, where
   * an announcement would be describing the furniture.
   */
  live?: 'assertive' | 'polite' | 'off';
};

/**
 * An inline banner in the page's own flow.
 *
 * Distinct from `ErrorState`, which *replaces* content that could not be loaded. A notice sits
 * beside content that is present but qualified: the list loaded, and something about the query it
 * answered needs saying — the cursor expired and the page was reset, permissions changed under the
 * reader, the export is capped. Those all leave usable rows on screen, so taking the screen away
 * to state them would be the wrong trade.
 */
export function Notice({
  tone = 'info',
  title,
  children,
  action,
  onDismiss,
  live = tone === 'danger' ? 'assertive' : 'polite',
}: NoticeProps) {
  return (
    <div
      className="pms-notice"
      data-tone={tone}
      /* `alert` carries an implicit assertive live region; `status` a polite one. Neither is set
       * as a bare `aria-live` on top of the role, which double-announces in some engines. */
      role={live === 'assertive' ? 'alert' : live === 'polite' ? 'status' : undefined}
    >
      <span className="pms-notice__icon" aria-hidden="true">
        {TONE_ICONS[tone]}
      </span>
      <div className="pms-notice__body">
        {title ? <p className="pms-notice__title">{title}</p> : null}
        <div className="pms-notice__text">{children}</div>
        {action ? <div className="pms-notice__action">{action}</div> : null}
      </div>
      {onDismiss ? (
        <IconButton label="Dismiss" icon={<CloseIcon size={14} />} onClick={onDismiss} />
      ) : null}
    </div>
  );
}
