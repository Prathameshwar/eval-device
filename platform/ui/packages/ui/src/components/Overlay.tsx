'use client';

import { useId, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { IconButton } from './IconButton';
import { CloseIcon } from './icons-console';
import { useDialogA11y } from '../lib/dialog';

/** `sm`/`md`/`lg` widen the panel; the exact widths live in `overlay.css`. */
export type OverlaySize = 'sm' | 'md' | 'lg';

type OverlayProps = {
  open: boolean;
  /** The heading, as a statement of what this is — "New customer", "Edit invoice". */
  title: ReactNode;
  children: ReactNode;
  /** Footer actions, right-aligned — usually a cancel and a primary button. */
  footer?: ReactNode;
  size?: OverlaySize;
  /** In flight: the close button disables, and Escape and the scrim stop dismissing. */
  busy?: boolean;
  /**
   * `false` for a step the user must complete or cancel through an explicit control: no header close
   * button, and neither the scrim nor Escape dismisses. The confirmation before something
   * irreversible is the case for it; an ordinary form is not.
   */
  dismissible?: boolean;
  onClose: () => void;
};

type OverlayVariant = 'modal' | 'drawer';

/**
 * The shared surface behind `Modal` and `Drawer`. Both are the same overlay —
 * portal, scrim, focus-trapped panel, one header/body/footer chrome — differing only in where the
 * panel sits and how it enters, so they share everything but the outer class. The chrome uses
 * `pms-overlay-*` classes common to both; only the frame (`pms-modal` / `pms-drawer`) varies.
 *
 * This is presentation. Authorization is server-side and enforced for every actor; a
 * form someone can close is not a control.
 */
function Overlay({
  variant,
  open,
  title,
  children,
  footer,
  size = 'md',
  busy = false,
  dismissible = true,
  onClose,
}: OverlayProps & { variant: OverlayVariant }) {
  const canDismiss = dismissible && !busy;
  const { panelRef, onKeyDown } = useDialogA11y({ open, onClose, dismissible: canDismiss });

  const baseId = useId();
  const titleId = `${baseId}-title`;
  const bodyId = `${baseId}-body`;
  const frame = variant === 'drawer' ? 'pms-drawer' : 'pms-modal';

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className={frame}>
      {/* Presentational: the panel owns Escape and the header/footer own dismissal, so the scrim
          carries no role or tab stop. */}
      <div
        className={`${frame}__scrim`}
        onMouseDown={() => {
          if (canDismiss) onClose();
        }}
      />
      <div
        ref={panelRef}
        className={`${frame}__panel`}
        data-size={size}
        role="dialog"
        tabIndex={-1}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        onKeyDown={onKeyDown}
      >
        <header className="pms-overlay-head">
          <h2 className="pms-overlay-title" id={titleId}>
            {title}
          </h2>
          {/* Kept visible but disabled while busy — the same call `ConfirmDialog` makes for Cancel —
              so the control does not vanish out from under a pointer heading for it. */}
          {dismissible ? (
            <IconButton
              label="Close"
              disabled={busy}
              icon={<CloseIcon size={16} />}
              onClick={onClose}
            />
          ) : null}
        </header>
        <div className="pms-overlay-body" id={bodyId}>
          {children}
        </div>
        {footer ? <footer className="pms-overlay-foot">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}

/**
 * A centred modal dialog — the container for a create/edit form or any focused task that should
 * take over the screen without leaving it. For the step before a destructive action, reach for
 * `ConfirmDialog`, which adds the typed-phrase gate and danger treatment.
 */
export function Modal(props: OverlayProps) {
  return <Overlay variant="modal" {...props} />;
}

/**
 * A side sheet anchored to the inline-end edge (right in LTR) — filters, a record's detail, or an
 * edit form that keeps the list it acts on in view. Same mechanism as `Modal`; it slides in from
 * the edge instead of centring.
 */
export function Drawer(props: OverlayProps) {
  return <Overlay variant="drawer" {...props} />;
}
