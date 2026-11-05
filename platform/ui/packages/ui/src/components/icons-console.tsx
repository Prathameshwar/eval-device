/*
 * Console line icons — the shell, the navigation and the dashboard's content grammar.
 *
 * Same drawing convention as `icons.tsx`: a 24×24 viewBox, `fill="none"`, strokes in
 * `currentColor` at 1.8 (2.2 for short marks), `aria-hidden` by default so an icon beside
 * a label isn't announced twice. A caller that uses an icon *as* the label passes
 * `aria-hidden={false}` and a title — see `IconButton`, which handles that for you.
 *
 * These carry no colour of their own; `currentColor` is what lets one icon read correctly
 * in all three themes and inside every signal tone.
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

/* ─────────────── theme switcher ─────────────── */

export function SunIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="4" stroke={S} strokeWidth="1.8" />
      <path
        d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"
        stroke={S}
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function MoonIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path
        d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.5 8.5 0 1 0 10.2 10.2Z"
        stroke={S}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** The `ledger` palette: warm paper. A half-filled disc reads as "a different paper". */
export function ContrastIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8.5" stroke={S} strokeWidth="1.8" />
      <path d="M12 3.5a8.5 8.5 0 0 1 0 17Z" fill={S} />
    </svg>
  );
}

export function MonitorIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="4.5" width="18" height="12" rx="1.6" stroke={S} strokeWidth="1.8" />
      <path d="M9 20h6M12 16.5V20" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/* ─────────────── shell chrome ─────────────── */

export function PanelCollapseIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="4" width="18" height="16" rx="2" stroke={S} strokeWidth="1.8" />
      <path d="M9.5 4v16" stroke={S} strokeWidth="1.8" />
      <path d="M17 9.5 14.5 12 17 14.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BellIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path
        d="M6.5 10a5.5 5.5 0 0 1 11 0c0 3.2.8 4.6 1.5 5.4.4.5.1 1.1-.6 1.1H5.6c-.7 0-1-.6-.6-1.1.7-.8 1.5-2.2 1.5-5.4Z"
        stroke={S}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M10 19.2a2.2 2.2 0 0 0 4 0" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function ChevronDownIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M6 9.5 12 15.5 18 9.5" stroke={S} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ChevronRightIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M9.5 6 15.5 12 9.5 18" stroke={S} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The switcher affordance: this control opens a list, it isn't a link. */
export function ChevronUpDownIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M8 10 12 6l4 4M8 14l4 4 4-4" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MenuIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 7h16M4 12h16M4 17h16" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function CloseIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M6 6l12 12M18 6 6 18" stroke={S} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function SearchIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="10.5" cy="10.5" r="6" stroke={S} strokeWidth="1.8" />
      <path d="M15 15l4.5 4.5" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function HelpIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8.5" stroke={S} strokeWidth="1.8" />
      <path
        d="M9.6 9.4a2.5 2.5 0 0 1 4.9.7c0 1.7-2.2 1.9-2.4 3.4M12 16.8v.4"
        stroke={S}
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function SettingsIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="2.8" stroke={S} strokeWidth="1.8" />
      <path
        d="M12 3.2 13.4 5.6l2.7-.6 1 2.6 2.4 1.4-.9 2.6.9 2.6-2.4 1.4-1 2.6-2.7-.6L12 20.8 10.6 18.4l-2.7.6-1-2.6L4.5 15l.9-2.6-.9-2.6 2.4-1.4 1-2.6 2.7.6Z"
        stroke={S}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LogoutIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14.5 4.5H19a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-4.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M13 12H4m3.5-3.5L4 12l3.5 3.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ─────────────── navigation: the billing domain ─────────────── */

export function DashboardIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.4" stroke={S} strokeWidth="1.8" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.4" stroke={S} strokeWidth="1.8" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.4" stroke={S} strokeWidth="1.8" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.4" stroke={S} strokeWidth="1.8" />
    </svg>
  );
}

export function CustomersIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="9" cy="8.5" r="3.2" stroke={S} strokeWidth="1.8" />
      <path d="M3.5 19.5a5.5 5.5 0 0 1 11 0" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M16 5.9a3.2 3.2 0 0 1 0 5.2M17.5 14.6a5.5 5.5 0 0 1 3 4.9" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function PaymentsIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="2.5" y="5.5" width="19" height="13" rx="2" stroke={S} strokeWidth="1.8" />
      <path d="M2.5 10h19" stroke={S} strokeWidth="1.8" />
      <path d="M6 14.5h3.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** Double-entry books: a bound ledger. */
export function BookIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 5.2A1.7 1.7 0 0 1 5.7 3.5H19a1 1 0 0 1 1 1v13.8H5.7A1.7 1.7 0 0 0 4 20V5.2Z" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M20 18.3v2.2H5.7" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8 8h8M8 11.5h5.5" stroke={S} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function StockIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3.5 8.5 12 4l8.5 4.5V19a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1V8.5Z" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <rect x="9" y="13" width="6" height="7" stroke={S} strokeWidth="1.8" />
    </svg>
  );
}

export function ReportsIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 20V4" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M4 20h16" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8.5 16.5v-5M13 16.5V7.5M17.5 16.5v-7" stroke={S} strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

export function TaxIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="7.8" cy="7.8" r="2.6" stroke={S} strokeWidth="1.8" />
      <circle cx="16.2" cy="16.2" r="2.6" stroke={S} strokeWidth="1.8" />
      <path d="M18.5 5.5 5.5 18.5" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function AuditIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M6.5 3.5h11a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1Z" stroke={S} strokeWidth="1.8" />
      <path d="M9 8.5h6M9 12h6" stroke={S} strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9 15.8l1.4 1.4 2.6-2.6" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function RolesIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="8" cy="12" r="3.5" stroke={S} strokeWidth="1.8" />
      <path d="M11.5 12H21M17.5 12v3.5M20 12v2.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/* ─────────────── content grammar ─────────────── */

export function FilterIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 7.5h16M7 12h10M10 16.5h4" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function RefreshIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M19.5 12a7.5 7.5 0 1 1-2.6-5.7" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
      <path d="M19.8 4.5v4h-4" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MoreIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="5.5" cy="12" r="1.7" fill={S} />
      <circle cx="12" cy="12" r="1.7" fill={S} />
      <circle cx="18.5" cy="12" r="1.7" fill={S} />
    </svg>
  );
}

export function CalendarIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3.5" y="5" width="17" height="15" rx="1.8" stroke={S} strokeWidth="1.8" />
      <path d="M3.5 9.5h17M8 3.5v3M16 3.5v3" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function ExternalLinkIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M10 5.5H5.5v13h13V14" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13.5 4.5h6v6M19 5 11 13" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ArrowRightIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4.5 12h14M13.5 7l5 5-5 5" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The warning triangle — every `warn` tone pairs its tint with this, never colour alone. */
export function WarnTriangleIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path
        d="M12 4.2 21 19.3a.8.8 0 0 1-.7 1.2H3.7a.8.8 0 0 1-.7-1.2L12 4.2Z"
        stroke={S}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M12 10v4M12 17v.4" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function XCircleIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8.5" stroke={S} strokeWidth="1.8" />
      <path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function CheckCircleIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8.5" stroke={S} strokeWidth="1.8" />
      <path d="M8.3 12.3l2.6 2.6 4.8-5.4" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function InfoIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8.5" stroke={S} strokeWidth="1.8" />
      <path d="M12 11v5.5M12 7.8v.4" stroke={S} strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function ClockIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8.5" stroke={S} strokeWidth="1.8" />
      <path d="M12 7.5V12l3.2 2" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function WalletIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3.5 7.5A2 2 0 0 1 5.5 5.5H18a1 1 0 0 1 1 1v1.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <rect x="3.5" y="7.5" width="17" height="11" rx="1.8" stroke={S} strokeWidth="1.8" />
      <circle cx="16.2" cy="13" r="1.4" fill={S} />
    </svg>
  );
}

export function TrendUpIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3.5 16.5 9 11l3.5 3.5L20 7" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14.5 7H20v5.5" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ActivityIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 12.5h4l2.5-6 4 12 2.5-6h5" stroke={S} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function DocumentIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M6 3.5h7.5L19 9v11.5H6z" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M13.5 3.5V9H19" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M9 13h7M9 16.5h4.5" stroke={S} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function MessageIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path
        d="M4 6a1.5 1.5 0 0 1 1.5-1.5h13A1.5 1.5 0 0 1 20 6v8.5a1.5 1.5 0 0 1-1.5 1.5H9l-5 4V6Z"
        stroke={S}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function UploadIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 15.5v-11M7.5 8.5 12 4l4.5 4.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4.5 18.5h15" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function DownloadIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3.5v11M7.5 10.5 12 15l4.5-4.5" stroke={S} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4.5 18.5h15" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
