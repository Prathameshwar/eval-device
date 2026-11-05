'use client';

import { useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { AlertIcon } from './icons';

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> & {
  label: string;
  /** Right-aligned note beside the label, e.g. "used to sign in". */
  optionalNote?: string;
  /** Right-aligned interactive element beside the label, e.g. a "Forgot?" link. */
  action?: ReactNode;
  hint?: ReactNode;
  error?: string;
  /** A small icon inside the input's leading edge (decorative; the label names the field). */
  leading?: ReactNode;
  /** Rendered inside the input wrap (e.g. a password show/hide toggle). */
  trailing?: ReactNode;
};

export function TextField({
  label,
  optionalNote,
  action,
  hint,
  error,
  leading,
  trailing,
  id,
  ...input
}: TextFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy =
    [input['aria-describedby'], error ? errorId : hint ? hintId : null]
      .filter(Boolean)
      .join(' ') || undefined;

  return (
    <div className="pms-field">
      <div className="pms-field__row">
        <label className="pms-label" htmlFor={inputId}>
          {label}
        </label>
        {action ?? (optionalNote ? <span className="pms-optional">{optionalNote}</span> : null)}
      </div>
      <div className="pms-input-wrap">
        {leading ? (
          <span className="pms-input__lead" aria-hidden="true">
            {leading}
          </span>
        ) : null}
        <input
          {...input}
          id={inputId}
          className={[
            'pms-input',
            leading ? 'pms-input--leading' : '',
            trailing ? 'pms-input--trailing' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          aria-invalid={error ? true : input['aria-invalid']}
          aria-describedby={describedBy}
        />
        {trailing}
      </div>
      {error ? (
        <p className="pms-error" id={errorId} role="alert">
          <AlertIcon size={14} />
          {error}
        </p>
      ) : hint ? (
        <p className="pms-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
