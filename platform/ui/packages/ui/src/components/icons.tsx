/* Shared line icons, drawn in currentColor so they inherit context. */
import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...rest }: IconProps) {
  return { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': true, ...rest };
}

export function EyeIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

export function EyeOffIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 4l16 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M9.5 5.7A10 10 0 0 1 12 5.5c6.4 0 10 6.5 10 6.5a17 17 0 0 1-3 3.7M6.2 7.9A17 17 0 0 0 2 12s3.6 6.5 10 6.5a10 10 0 0 0 3-.45" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function CheckIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M5 12.5 10 17 19 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BackIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14 6l-6 6 6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function AlertIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <path d="M12 7v6M12 16.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function MailIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 6h16v12H4z" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Billing — an invoice/receipt with a torn foot. */
export function ReceiptIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M7 3h10v18l-2-1.3-1.7 1.3-1.7-1.3-1.6 1.3L7 21z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M10 8h4M10 11.5h4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** Accounting — a balance scale: debits equal credits. */
export function ScaleIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 4v15M8 21h8M5 7h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M5 7l-2.5 5h5zM19 7l-2.5 5h5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

/** Inventory — a box/carton. */
export function BoxIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3 20 7v10l-8 4-8-4V7z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M4 7l8 4 8-4M12 11v10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Trust — a shield with a check. */
export function ShieldIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3 5 6v6c0 4 3 6.6 7 8 4-1.4 7-4 7-8V6z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A padlock — password fields. */
export function LockIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** A person — name fields. */
export function UserIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** A phone — mobile-number fields. */
export function PhoneIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="7" y="3" width="10" height="18" rx="2.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M10.5 18h3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** A storefront — business-name fields. */
export function StoreIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M5 9h14v11H5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M5 9l1.5-4h11L19 9" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M10 20v-5h4v5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

/** Google — the four-colour "G" brand mark (its own colours, not the PMS palette). */
export function GoogleIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.5-5.2 3.5-8.8z" />
      <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24z" />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.3a12 12 0 0 0 0 10.8l4-3.1z" />
      <path fill="#EA4335" d="M12 4.8c1.8 0 3.4.6 4.6 1.8l3.5-3.5A12 12 0 0 0 1.3 6.6l4 3.1C6.2 6.9 8.9 4.8 12 4.8z" />
    </svg>
  );
}

/** Facebook — the "f" brand mark in Facebook blue. */
export function FacebookIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="#1877F2"
        d="M24 12a12 12 0 1 0-13.9 11.9v-8.4H7v-3.5h3.1V9.4c0-3 1.8-4.7 4.6-4.7 1.3 0 2.7.2 2.7.2v3h-1.5c-1.5 0-2 .9-2 1.9v2.2h3.4l-.6 3.5h-2.8v8.4A12 12 0 0 0 24 12z"
      />
    </svg>
  );
}
