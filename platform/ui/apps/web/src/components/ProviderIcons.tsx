/**
 * Third-party sign-in marks the design system does not ship.
 *
 * `@pms/ui` provides `GoogleIcon` and `FacebookIcon`; Microsoft is missing, and a vendor mark is
 * not a design-system icon anyway — it is the vendor's trademark, drawn to their spec, and the one
 * kind of icon that must *not* inherit `currentColor`. So it lives with the app that uses it.
 */

type IconProps = { size?: number };

export function MicrosoftIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2" y="2" width="9" height="9" fill="#f25022" />
      <rect x="13" y="2" width="9" height="9" fill="#7fba00" />
      <rect x="2" y="13" width="9" height="9" fill="#00a4ef" />
      <rect x="13" y="13" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}
