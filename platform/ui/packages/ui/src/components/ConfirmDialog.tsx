'use client';

import { useEffect, useId, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Button } from './Button';
import { AlertIcon } from './icons';
import { useDialogA11y } from '../lib/dialog';

type ConfirmDialogProps = {
  open: boolean;
  /** The question, as a decision: "Delete 3 customers?" — not "Are you sure?". */
  title: string;
  /** What will actually happen, and what cannot be undone. */
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** `danger` tints the confirm button and starts focus on Cancel. */
  tone?: 'default' | 'danger';
  /**
   * Typed-phrase gate for an irreversible act — `delete`, `LOCK FY2026`. Confirm stays disabled
   * until the phrase is typed; matching is trimmed and case-insensitive, because the words are the
   * proof of intent, not the capitalisation, and a caps-lock that blocks a correct phrase is only
   * friction. Reserved for the few actions that cannot be reversed by a compensating entry; on
   * everything else it is friction that trains people to type past it.
   */
  confirmPhrase?: string;
  /** In flight: the confirm button spins, Cancel, Escape and the scrim stop dismissing. */
  busy?: boolean;
  /** A failed attempt. The dialog stays open so the user can retry or cancel. */
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * The confirmation step in front of a destructive or irreversible action.
 *
 * A modal dialog, and unlike `Menu` it *does* trap focus: `aria-modal` tells assistive tech the
 * rest of the page is inert, so letting Tab wander into it would contradict what was announced.
 *
 * This is presentation. The action behind it is authorized server-side, and irreversibility is
 * enforced in `domain/` for every actor — a dialog someone can close is not a control.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'default',
  confirmPhrase,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('');
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const bodyId = `${baseId}-body`;
  const phraseId = `${baseId}-phrase`;

  const phraseSatisfied =
    confirmPhrase === undefined ||
    typed.trim().toLowerCase() === confirmPhrase.trim().toLowerCase();
  const canConfirm = phraseSatisfied && !busy;

  /*
   * The focus trap, Escape and focus restore are the shared dialog mechanism (`lib/dialog`). What
   * stays here is this dialog's own safety decision — where focus *starts*: on a destructive dialog
   * it starts on Cancel, so a stray Enter from the keypress that opened it dismisses rather than
   * deletes; a typed-phrase dialog starts in the input, since nothing can fire yet anyway. Not while
   * busy: the request cannot be recalled, so dismissing would leave the user believing nothing
   * happened.
   */
  const { panelRef, onKeyDown } = useDialogA11y({
    open,
    onClose: onCancel,
    dismissible: !busy,
    initialFocus: (panel) =>
      panel?.querySelector<HTMLElement>(
        confirmPhrase !== undefined
          ? '[data-dialog-phrase]'
          : tone === 'danger'
            ? '[data-dialog-cancel]'
            : '[data-dialog-confirm]',
      ) ?? null,
  });

  // A reopened dialog must not still hold the phrase from last time, or the second irreversible
  // action confirms on one click.
  useEffect(() => {
    if (!open) setTyped('');
  }, [open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="pms-dialog" data-tone={tone === 'danger' ? 'danger' : undefined}>
      {/* Presentational: the dialog owns Escape and the buttons own dismissal, so this is not a
          control and carries no role or tab stop. */}
      <div
        className="pms-dialog__scrim"
        onMouseDown={() => {
          if (!busy) onCancel();
        }}
      />
      <div
        ref={panelRef}
        className="pms-dialog__panel"
        role="dialog"
        tabIndex={-1}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        onKeyDown={onKeyDown}
      >
        <div className="pms-dialog__header">
          {/* The destructive dialog earns a mark the ordinary one does not: a danger-tinted badge
              beside the title, so the tone is legible before the copy is read. An icon on every
              dialog is an icon that means nothing, so `default` stays unadorned. Decorative — the
              tone is already carried by the copy and the confirm button, so it is hidden from AT. */}
          {tone === 'danger' ? (
            <span className="pms-dialog__icon" aria-hidden="true">
              <AlertIcon size={18} />
            </span>
          ) : null}
          <h2 className="pms-dialog__title" id={titleId}>
            {title}
          </h2>
        </div>
        <div className="pms-dialog__body" id={bodyId}>
          {children}
        </div>

        {confirmPhrase !== undefined ? (
          <div className="pms-dialog__phrase">
            <label className="pms-label" htmlFor={phraseId}>
              Type <code className="pms-dialog__phrase-code">{confirmPhrase}</code> to confirm
            </label>
            <input
              id={phraseId}
              data-dialog-phrase=""
              className="pms-input"
              value={typed}
              // Off for all three: a browser suggesting the phrase, or correcting its case, would
              // defeat the point of asking someone to type it.
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              disabled={busy}
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
        ) : null}

        {error ? (
          <p className="pms-dialog__error" role="alert">
            <AlertIcon size={14} />
            {error}
          </p>
        ) : null}

        <div className="pms-dialog__actions">
          <Button
            type="button"
            variant="ghost"
            data-dialog-cancel=""
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            data-dialog-confirm=""
            variant={tone === 'danger' ? 'danger' : 'primary'}
            loading={busy}
            disabled={!canConfirm}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
