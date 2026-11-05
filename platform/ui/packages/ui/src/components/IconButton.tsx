import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'title'> & {
  /**
   * Required. An icon-only control with no accessible name is invisible to a screen
   * reader and unlabelled on hover, so the label is not optional — it becomes both the
   * `aria-label` and the native tooltip.
   */
  label: string;
  icon: ReactNode;
  variant?: 'ghost' | 'outline';
  /** Renders a dot over the icon — an unread marker. Never the only signal: see `label`. */
  badged?: boolean;
};

/**
 * A square, icon-only button: the top bar's refresh / overflow / collapse controls.
 * Deliberately not a `Button` variant — its whole contract is that the label is a name
 * rather than visible content.
 *
 * The ref is forwarded because an icon button is what an anchored popover hangs off: `Menu`
 * measures its trigger to place the panel and returns focus to it on Escape, and neither is
 * possible through a wrapper element.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, variant = 'ghost', badged = false, className = '', type = 'button', ...rest },
  ref,
) {
  const classes = ['pms-btn', 'pms-btn--icon', `pms-btn--icon-${variant}`, className]
    .filter(Boolean)
    .join(' ');

  return (
    <button ref={ref} type={type} className={classes} aria-label={label} title={label} {...rest}>
      <span className="pms-btn__icon" aria-hidden="true">
        {icon}
      </span>
      {badged ? <span className="pms-btn__dot" aria-hidden="true" /> : null}
    </button>
  );
});
