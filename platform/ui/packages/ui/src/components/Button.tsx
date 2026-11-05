import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** `danger` is the confirming action of a destructive step — never a page's default action. */
  variant?: 'primary' | 'ghost' | 'danger';
  block?: boolean;
  /** Shows a spinner and disables the button; keeps the accessible name via `loadingLabel`. */
  loading?: boolean;
  loadingLabel?: string;
  children: ReactNode;
};

export function Button({
  variant = 'primary',
  block = false,
  loading = false,
  loadingLabel = 'Working…',
  className = '',
  disabled,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    'pms-btn',
    `pms-btn--${variant}`,
    block ? 'pms-btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      {...rest}
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || rest['aria-busy']}
    >
      {loading ? (
        <>
          <span className="pms-btn__spinner" aria-hidden="true" />
          {loadingLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
}
