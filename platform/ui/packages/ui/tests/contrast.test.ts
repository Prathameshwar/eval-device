/**
 * Contrast, computed rather than claimed.
 *
 * §2.4 has always stated the gates — body text ≥ 4.5:1, large text and UI boundaries ≥ 3:1,
 * in all three palettes — and nothing checked them. That is decision log #13's failure mode
 * exactly: the chart tokens were hue-picked, the doc asserted they passed, and they did not.
 * Anything about colour that can be computed gets computed, or the next re-tint quietly
 * reintroduces a 2.6:1 axis label.
 *
 * The theme files are read as text, never imported: these are the values that ship, and
 * jsdom resolves no custom properties anyway.
 *
 * WHY THE PAIRING TABLE IS WRITTEN OUT BY HAND, rather than crossing every ink with every
 * surface: a cross-product asserts pairings that never render — `--pms-warn-ink` on
 * `--pms-success-tint`, `--pms-chart-6` on `--pms-danger-tint` — and every one of them
 * would then need an individual suppression. A suppression list is a place for a real
 * pairing to hide. So each row below is a pairing some stylesheet actually produces, and it
 * carries the gate that *that use* owes: 4.5 where the token is text, 3 where it is the
 * boundary of a control or a graphic that carries meaning. Adding a row is the cost of
 * introducing a new pairing, and that is the point.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const STYLES = join(__dirname, '..', 'src', 'styles');

const THEMES = ['light', 'dark', 'ledger'] as const;
type Theme = (typeof THEMES)[number];

/** The gates of §2.4. `TEXT` is body text; `GRAPHIC` is large text, a control edge, a mark. */
const TEXT = 4.5;
const GRAPHIC = 3;

type Rgb = readonly [number, number, number];

// ---------- WCAG 2.1 relative luminance and contrast ratio ----------

/** 8-bit sRGB channel → linear-light, per WCAG 2.1 relative-luminance definition. */
function toLinear(channel: number): number {
  const c = channel / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgb): number {
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [lighter, darker] = la > lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * The gates are stated to one decimal ("4.5:1", "3:1") and that is the precision they are
 * compared at, so a measured 4.48 counts as meeting 4.5. This absorbs the rounding in the
 * theme files' own recorded numbers and nothing more — a real miss (3.95 against 4.5) is
 * half a point away and still fails.
 */
function meets(ratio: number, gate: number): boolean {
  return Math.round(ratio * 10) / 10 >= gate;
}

// ---------- colour parsing ----------

function parseHex(hex: string): Rgb {
  const h = hex.replace('#', '');
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h;
  return [
    Number.parseInt(full.slice(0, 2), 16),
    Number.parseInt(full.slice(2, 4), 16),
    Number.parseInt(full.slice(4, 6), 16),
  ];
}

/** `rgba(r, g, b, a)` composited over an opaque backdrop — a translucent token has no
 * contrast of its own, only one against the thing stated to be behind it. */
function compositeRgba(value: string, backdrop: Rgb): Rgb {
  const parts = (value.match(/rgba?\(([^)]+)\)/)?.[1] ?? '')
    .split(',')
    .map((p) => Number.parseFloat(p.trim()));
  const alpha = parts.length > 3 ? (parts[3] as number) : 1;
  return [0, 1, 2].map(
    (i) => (parts[i] as number) * alpha + (backdrop[i] as number) * (1 - alpha),
  ) as unknown as Rgb;
}

/** Every `--pms-*` declaration in one theme file, as written. */
function declarations(theme: Theme): Map<string, string> {
  const css = readFileSync(join(STYLES, `theme-${theme}.css`), 'utf8');
  const map = new Map<string, string>();
  for (const match of css.matchAll(/(--pms-[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    map.set(match[1] as string, (match[2] as string).trim());
  }
  return map;
}

const TOKENS: Record<Theme, Map<string, string>> = {
  light: declarations('light'),
  dark: declarations('dark'),
  ledger: declarations('ledger'),
};

/** A token's colour, composited over `backdrop` when the token is translucent. */
function resolve(theme: Theme, token: string, backdrop: Rgb): Rgb {
  const value = TOKENS[theme].get(token);
  if (value === undefined) throw new Error(`${theme}: ${token} is not declared`);
  if (value.startsWith('#')) return parseHex(value);
  if (value.startsWith('rgb')) return compositeRgba(value, backdrop);
  throw new Error(`${theme}: ${token} is not a flat colour (${value})`);
}

/** The colour stops of a gradient token, in order. */
function gradientStops(theme: Theme, token: string): Rgb[] {
  const value = TOKENS[theme].get(token);
  if (value === undefined) throw new Error(`${theme}: ${token} is not declared`);
  const stops = [...value.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => parseHex(m[0]));
  if (stops.length < 2) throw new Error(`${theme}: ${token} has no colour stops`);
  return stops;
}

// ---------- the pairings ----------

type Pair = {
  /** The foreground token. */
  fg: string;
  /** What is behind it. */
  bg: string;
  gate: number;
  /** Where this pairing comes from — so a future edit can find the rule it protects. */
  why: string;
};

const SURFACES = ['--pms-paper', '--pms-surface', '--pms-surface-2', '--pms-overlay'];

const PAIRS: Pair[] = [
  // — Text on every surface it can land on. The four surfaces are the page, a card, a tile
  //   nested in a card, and a menu, and body copy appears on all four.
  ...SURFACES.map((bg) => ({ fg: '--pms-ink', bg, gate: TEXT, why: 'body text' })),
  ...SURFACES.map((bg) => ({
    fg: '--pms-ink-soft',
    bg,
    gate: TEXT,
    why: 'secondary text — lede, hints, card subtitles, chart ticks and the chart annotation',
  })),
  // `ink-faint` carries 11px overlines, input placeholders and list ranks…
  {
    fg: '--pms-ink-faint',
    bg: '--pms-paper',
    gate: TEXT,
    why: 'page overlines and the footer copyright, on the page surface',
  },
  {
    fg: '--pms-ink-faint',
    bg: '--pms-surface',
    gate: TEXT,
    why: 'rail section labels, input placeholders, list-row ranks, on a card or the rail',
  },
  // …and it is held to the text gate on `surface-2` and `overlay` too. These two were
  // briefly relaxed to the graphic gate on the argument that only glyphs land there, but the
  // token was then lifted so it clears 4.5 on every surface — and the argument was fragile:
  // it depended on nobody ever putting `ink-faint` text on a nested tile or in a menu, which
  // is not a property anything enforces.
  {
    fg: '--pms-ink-faint',
    bg: '--pms-surface-2',
    gate: TEXT,
    why: 'the org code and nested-tile labels, on a nested surface',
  },
  {
    fg: '--pms-ink-faint',
    bg: '--pms-overlay',
    gate: TEXT,
    why: 'user-menu item labels and icons, on a popover',
  },

  // — Disabled. Kept at the text gate rather than leaning on WCAG's inactive-component
  //   exemption: a disabled total is still a number someone needs to read.
  {
    fg: '--pms-disabled-ink',
    bg: '--pms-disabled-surface',
    gate: TEXT,
    why: 'a disabled input or button',
  },

  // — `SearchSelect` (§5.5). Its list is an overlay, and its highlighted row introduces a
  //   surface no other component uses — `--pms-selected` — so every colour that lands on it
  //   is measured rather than assumed.
  {
    fg: '--pms-ink',
    bg: '--pms-selected',
    gate: TEXT,
    why: 'the highlighted option in a SearchSelect list',
  },
  {
    fg: '--pms-ink-soft',
    bg: '--pms-selected',
    gate: TEXT,
    why: 'the meta line of a highlighted option — a code, a place, a status',
  },
  {
    fg: '--pms-brand-ink',
    bg: '--pms-selected',
    gate: TEXT,
    why: 'an already-selected option that is also highlighted',
  },
  {
    fg: '--pms-brand',
    bg: '--pms-overlay',
    gate: TEXT,
    why: 'the “Add …” create row, and the check mark on a selected option',
  },
  {
    fg: '--pms-brand',
    bg: '--pms-selected',
    gate: GRAPHIC,
    why: 'the 2px marker on the highlighted row — the non-colour cue that survives greyscale',
  },
  {
    fg: '--pms-disabled-ink',
    bg: '--pms-overlay',
    gate: TEXT,
    why: 'an option present but not selectable — an inactive customer still has to be readable',
  },
  {
    fg: '--pms-brand',
    bg: '--pms-selected',
    gate: TEXT,
    why: 'the “Add …” create row while it is the highlighted row',
  },
  {
    fg: '--pms-disabled-ink',
    bg: '--pms-selected',
    gate: TEXT,
    why: 'a disabled option under the highlight — hovering one is allowed, selecting it is not',
  },
  {
    fg: '--pms-brand',
    bg: '--pms-hover',
    gate: TEXT,
    why: 'the “Load more” control on hover',
  },

  // — Links and brand text.
  { fg: '--pms-brand', bg: '--pms-surface', gate: TEXT, why: 'links, the selected tab' },
  { fg: '--pms-brand', bg: '--pms-paper', gate: TEXT, why: 'links in page-level copy' },
  {
    fg: '--pms-brand-ink',
    bg: '--pms-brand-tint',
    gate: TEXT,
    why: 'the selected rail item, a brand badge, an avatar’s initials',
  },

  // — Signals are used as triplets, so each `-ink` is only ever measured on its own `-tint`
  //. This is why the table is not a cross-product.
  ...(['success', 'warn', 'danger', 'info', 'neutral'] as const).map((signal) => ({
    fg: `--pms-${signal}-ink`,
    bg: `--pms-${signal}-tint`,
    gate: TEXT,
    why: `the ${signal} badge, stat tile and list row`,
  })),

  // — Control boundaries (WCAG 1.4.11). An empty input, an unchecked checkbox, an icon-only
  //   outline button and the theme-switcher group are defined by nothing but this hairline.
  {
    fg: '--pms-control-line',
    bg: '--pms-surface',
    gate: GRAPHIC,
    why: 'input, checkbox and icon-outline button edges on a card',
  },
  {
    fg: '--pms-control-line',
    bg: '--pms-paper',
    gate: GRAPHIC,
    why: 'the same controls sitting straight on the page',
  },
  {
    fg: '--pms-control-line',
    bg: '--pms-surface-2',
    gate: GRAPHIC,
    why: 'the theme-switcher group border against its own fill',
  },

  // — Focus is visible at every stop (§6), so the ring is measured on every surface a
  //   focusable thing can sit on.
  ...SURFACES.map((bg) => ({
    fg: '--pms-focus',
    bg,
    gate: GRAPHIC,
    why: 'the 2px solid stop of --pms-focus-ring',
  })),

  // — Charts: eight series and the zero line, all against the card they are drawn on.
  ...Array.from({ length: 8 }, (_, i) => ({
    fg: `--pms-chart-${i + 1}`,
    bg: '--pms-surface',
    gate: GRAPHIC,
    why: `series ${i + 1} bars — data ink`,
  })),
  {
    fg: '--pms-chart-axis',
    bg: '--pms-surface',
    gate: GRAPHIC,
    why: 'the zero line the bars grow out of',
  },
];

/** The primary action is a gradient, so its label is measured against both stops. */
const GRADIENT_PAIRS = [
  {
    fg: '--pms-ink-invert',
    gradient: '--pms-grad-action',
    gate: TEXT,
    why: 'the primary button label and the checked tick',
  },
] as const;

// ---------- the assertions ----------

describe('contrast (design-system §2.4)', () => {
  it('computes the WCAG reference ratios correctly — the measuring stick first', () => {
    expect(contrast([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 5);
    expect(contrast([255, 255, 255], [255, 255, 255])).toBeCloseTo(1, 5);
    // The documented mid-grey: #767676 is the canonical 4.54:1 on white.
    expect(contrast(parseHex('#767676'), [255, 255, 255])).toBeCloseTo(4.54, 2);
    // A translucent value has contrast only against a stated backdrop.
    expect(compositeRgba('rgba(0, 0, 0, 0.5)', [255, 255, 255])).toEqual([127.5, 127.5, 127.5]);
  });

  describe.each(THEMES)('%s', (theme) => {
    it.each(PAIRS)('$fg on $bg ≥ $gate:1 — $why', ({ fg, bg, gate, why }) => {
      const background = resolve(theme, bg, [255, 255, 255]);
      const foreground = resolve(theme, fg, background);
      const ratio = contrast(foreground, background);

      // The failure message is the deliverable: theme, pair, what it is for, and the number.
      expect(
        meets(ratio, gate)
          ? 'meets gate'
          : `${theme}: ${fg} on ${bg} measures ${ratio.toFixed(2)}:1, gate ${gate}:1 (${why})`,
      ).toBe('meets gate');
    });

    it.each(GRADIENT_PAIRS)(
      '$fg on both stops of $gradient ≥ $gate:1 — $why',
      ({ fg, gradient, gate, why }) => {
        const failures = gradientStops(theme, gradient)
          .map((stop) => ({ stop, ratio: contrast(resolve(theme, fg, stop), stop) }))
          .filter(({ ratio }) => !meets(ratio, gate))
          .map(
            ({ stop, ratio }) =>
              `${theme}: ${fg} on ${gradient} stop rgb(${stop.join(', ')}) measures ` +
              `${ratio.toFixed(2)}:1, gate ${gate}:1 (${why})`,
          );

        expect(failures).toEqual([]);
      },
    );
  });

  it('measures every token the table names, in every palette', () => {
    const named = new Set([
      ...PAIRS.flatMap(({ fg, bg }) => [fg, bg]),
      ...GRADIENT_PAIRS.flatMap(({ fg, gradient }) => [fg, gradient]),
    ]);
    for (const theme of THEMES) {
      const missing = [...named].filter((token) => !TOKENS[theme].has(token));
      expect({ theme, missing }).toEqual({ theme, missing: [] });
    }
  });
});
