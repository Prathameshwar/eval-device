/*
 * Table line icons — sorting, paging, row verbs and the column controls.
 *
 * Same drawing convention as `icons.tsx` and `icons-console.tsx`: a 24×24 viewBox, `fill="none"`,
 * strokes in `currentColor` at 1.8 (2.2 for short marks), `aria-hidden` by default so an icon
 * beside a label isn't announced twice. A caller that uses an icon *as* the label passes it to
 * `IconButton`, which supplies the name.
 *
 * These carry no colour of their own; `currentColor` is what lets one icon read correctly in all
 * three themes and inside every signal tone — and is what keeps this file out of the
 * colour-literal exception list in `tokens.test.ts`.
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

/* ─────────────── sorting and paging ─────────────── */

/**
 * The ascending sort mark. `ChevronDownIcon` is descending and `ChevronUpDownIcon` is the
 * unsorted-but-sortable affordance, so the trio is complete once this exists.
 */
export function ChevronUpIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M6 14.5 12 8.5 18 14.5" stroke={S} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ChevronLeftIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M14.5 6 8.5 12 14.5 18" stroke={S} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** "Back to the first page" — the only jump a cursor-paged list can honestly offer. */
export function ChevronsLeftIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M11 6 5 12 11 18M18.5 6l-6 6 6 6" stroke={S} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ChevronsRightIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M13 6l6 6-6 6M5.5 6l6 6-6 6" stroke={S} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * The row overflow ("kebab"). Vertical, unlike `MoreIcon`: a horizontal ellipsis in the last
 * column of a table reads as truncated content rather than as a control.
 */
export function MoreVerticalIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="5.5" r="1.7" fill={S} />
      <circle cx="12" cy="12" r="1.7" fill={S} />
      <circle cx="12" cy="18.5" r="1.7" fill={S} />
    </svg>
  );
}

/* ─────────────── row verbs ─────────────── */

export function PlusIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 5v14M5 12h14" stroke={S} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function EditIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4.5 19.5h4l10-10a2.1 2.1 0 0 0-3-3l-10 10v3Z" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M14.5 6.5l3 3" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function TrashIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4.5 7h15" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M9.5 7V4.8h5V7" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M6.5 7l.9 12.2a1 1 0 0 0 1 .9h7.2a1 1 0 0 0 1-.9L17.5 7" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M10.5 11v5.5M13.5 11v5.5" stroke={S} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function CopyIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="9" y="9" width="11" height="11" rx="1.8" stroke={S} strokeWidth="1.8" />
      <path d="M15 6.5V5.8a1.8 1.8 0 0 0-1.8-1.8H5.8A1.8 1.8 0 0 0 4 5.8v7.4A1.8 1.8 0 0 0 5.8 15h.7" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/* ─────────────── column and layout controls ─────────────── */

/** Which columns are shown. Three tracks, one dimmed — "some of these are hidden". */
export function ColumnsIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="1.8" stroke={S} strokeWidth="1.8" />
      <path d="M9.2 4.5v15M14.8 4.5v15" stroke={S} strokeWidth="1.6" />
    </svg>
  );
}

/** Row height. Tighter spacing at the bottom is the whole idea of "compact". */
export function DensityIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 5.5h16M4 10.5h16M4 14.5h16M4 18h16" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** Grab handle for a reorderable row in the column picker. */
export function DragHandleIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="9.5" cy="6.5" r="1.5" fill={S} />
      <circle cx="14.5" cy="6.5" r="1.5" fill={S} />
      <circle cx="9.5" cy="12" r="1.5" fill={S} />
      <circle cx="14.5" cy="12" r="1.5" fill={S} />
      <circle cx="9.5" cy="17.5" r="1.5" fill={S} />
      <circle cx="14.5" cy="17.5" r="1.5" fill={S} />
    </svg>
  );
}

/** A column pinned against horizontal scroll. */
export function PinIcon(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M9 3.5h6l-.8 5.2 3.3 3.3v1.5H6.5V12l3.3-3.3L9 3.5Z" stroke={S} strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M12 13.5v7" stroke={S} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
