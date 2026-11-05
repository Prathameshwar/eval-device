'use client';
import { useId, type TextareaHTMLAttributes } from 'react';
export function FormTextArea({
  label,
  hint,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="pms-field">
      <label className="pms-label" htmlFor={id}>
        {label}
      </label>
      <textarea
        {...props}
        id={id}
        className="pms-input"
        rows={props.rows ?? 3}
        aria-describedby={hint ? id + '-hint' : undefined}
      />
      {hint ? (
        <p id={id + '-hint'} className="pms-meta">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
