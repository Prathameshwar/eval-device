/*
 * AI Evaluator's own icons — the six the design system has no equivalent for.
 *
 * They live in the app for the same reason the logo does: "tenant", "device", "model" and
 * "session" are this product's vocabulary, and a second consumer of `@pms/ui` should not inherit
 * them. If the console and another app both end up needing these, promote them to the package
 * then — with two callers proving the need.
 *
 * Drawing convention copied exactly from `icons-console.tsx`, so these sit correctly beside the
 * package's own: a 24×24 viewBox, `fill="none"`, strokes in `currentColor` at 1.8 (2.2 for short
 * marks), `aria-hidden` by default, and no colour of their own — which is what lets one icon read
 * correctly in all three palettes and inside every signal tone.
 */
import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    'aria-hidden': true,
    ...rest,
  };
}

const S = 'currentColor';

/** A tenant — an institution, drawn as a building rather than a person or a folder. */
export function TenantIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 20.5V6.2a1 1 0 0 1 .7-1l7-2.1a1 1 0 0 1 1.3 1v16.4" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M13 9.5h6a1 1 0 0 1 1 1v10" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M2.8 20.5h18.4" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M7 8.4v1.2M7 13v1.2M9.8 8.4v1.2M9.8 13v1.2M16.3 13.4v1.2" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/**
 * A device — the enrolled appliance, not a monitor. The package's `MonitorIcon` is a desktop
 * screen, which is the thing an administrator sits at rather than the thing being managed.
 */
export function DeviceIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3.2" y="7.5" width="17.6" height="11" rx="1.8" stroke={S} strokeWidth="1.8" />
      <path d="M7 11.3h5" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="17" cy="11.4" r="1.15" fill={S} />
      <path d="M7 14.9h10" stroke={S} strokeWidth="1.6" strokeLinecap="round" />
      <path d="M12 7.5V4.4M9.4 3.2h5.2" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** A model — a processor die with connector pins. */
export function ModelIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2" stroke={S} strokeWidth="1.8" />
      <rect x="10.2" y="10.2" width="3.6" height="3.6" rx="0.9" stroke={S} strokeWidth="1.6" />
      <path d="M9.6 3.4v3.1M14.4 3.4v3.1M9.6 17.5v3.1M14.4 17.5v3.1M3.4 9.6h3.1M3.4 14.4h3.1M17.5 9.6h3.1M17.5 14.4h3.1" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** Live — a trace with a pulse, for the count of devices currently reporting. */
export function PulseIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="4.5" width="18" height="15" rx="2.2" stroke={S} strokeWidth="1.8" />
      <path d="M6.4 12.2h2.4l1.7-3.6 2.6 7.2 1.7-3.6h2.8" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A licence — a document with a seal, distinct from `DocumentIcon` and `AuditIcon`. */
export function LicenseIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M18.5 10.6V4.5a1 1 0 0 0-1-1h-11a1 1 0 0 0-1 1v15a1 1 0 0 0 1 1h5" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8.6 7.6h6.8M8.6 11.2h4.2" stroke={S} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="16.6" cy="15.6" r="3.1" stroke={S} strokeWidth="1.8" />
      <path d="M14.8 18.2 14.2 21.4l2.4-1.2 2.4 1.2-.6-3.2" stroke={S} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A practice session — two turns of a conversation. */
export function SessionIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3.5 8.2a2 2 0 0 1 2-2h8.4a2 2 0 0 1 2 2v4.1a2 2 0 0 1-2 2H8.2L4.6 17V8.2Z" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M18 9.8h.5a2 2 0 0 1 2 2V21l-2.8-2.6h-4.3a2 2 0 0 1-2-2v-.3" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
