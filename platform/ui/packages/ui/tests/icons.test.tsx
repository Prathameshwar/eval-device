/**
 * Every icon, rendered.
 *
 * Individually these are trivial, which is exactly why a typo in one goes unnoticed until
 * someone opens the screen that uses it. Rendering all of them asserts the shared
 * contract — 24×24 box, `currentColor` strokes, hidden from assistive technology by
 * default, caller-controlled size — in one place, rather than per icon at each call site.
 */
import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import * as authIcons from '../src/components/icons';
import * as consoleIcons from '../src/components/icons-console';
import * as tableIcons from '../src/components/icons-table';

type IconComponent = (props: { size?: number }) => ReactElement;

function iconsIn(module: Record<string, unknown>): [string, IconComponent][] {
  return Object.entries(module)
    .filter(([name]) => name.endsWith('Icon'))
    .map(([name, value]) => [name, value as IconComponent]);
}

const AUTH_ICONS = iconsIn(authIcons);
const CONSOLE_ICONS = iconsIn(consoleIcons);
const TABLE_ICONS = iconsIn(tableIcons);
const ALL_ICONS = [...AUTH_ICONS, ...CONSOLE_ICONS, ...TABLE_ICONS];

/**
 * The two third-party glyphs. Their brand colours are mandated and they
 * are filled marks rather than strokes, so the line-icon contract genuinely does not apply
 * to them — they get their own assertions below.
 */
const BRAND_GLYPHS = new Set(['GoogleIcon', 'FacebookIcon']);
const LINE_ICONS = ALL_ICONS.filter(([name]) => !BRAND_GLYPHS.has(name));

describe('icons', () => {
  it('exports the full set the shell, the nav and the content grammar need', () => {
    // A guard against an icon silently disappearing from the barrel during a refactor.
    expect(AUTH_ICONS.length).toBeGreaterThanOrEqual(16);
    expect(CONSOLE_ICONS.length).toBeGreaterThanOrEqual(40);
    expect(TABLE_ICONS.length).toBeGreaterThanOrEqual(13);
  });

  it('draws the kebab vertically, so it does not read as truncated cell content', () => {
    const { container } = render(<tableIcons.MoreVerticalIcon />);
    const dots = [...container.querySelectorAll('circle')];

    expect(dots).toHaveLength(3);
    // Same x, three different y: a horizontal ellipsis in the last column looks like "…".
    expect(new Set(dots.map((dot) => dot.getAttribute('cx'))).size).toBe(1);
    expect(new Set(dots.map((dot) => dot.getAttribute('cy'))).size).toBe(3);
  });

  it.each(LINE_ICONS)('%s renders a 24-unit square, hidden from AT by default', (_name, Icon) => {
    const { container } = render(<Icon />);
    const svg = container.querySelector('svg');

    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
    expect(svg).toHaveAttribute('fill', 'none');
    // Hidden by default: an icon beside a text label would otherwise be announced twice.
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg?.getAttribute('width')).toBe('18');
    expect(svg?.getAttribute('height')).toBe('18');
    // Something must actually be drawn — an empty svg is the failure this catches.
    expect(svg?.children.length).toBeGreaterThan(0);
  });

  it.each(ALL_ICONS)('%s takes its size from the caller', (_name, Icon) => {
    const { container } = render(<Icon size={32} />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('width', '32');
    expect(svg).toHaveAttribute('height', '32');
  });

  it.each(LINE_ICONS)(
    '%s inherits its colour, so it reads in all three themes and every tone',
    (_name, Icon) => {
      const { container } = render(<Icon />);
      const markup = container.innerHTML;

      // A hardcoded colour here is a theme bug waiting to happen: the same glyph appears on
      // a brand fill, inside a warn tint, and on a dark surface.
      expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(markup).not.toMatch(/\brgba?\(|\bhsla?\(/);
      expect(markup).toContain('currentColor');
    },
  );

  it.each([...BRAND_GLYPHS])('%s keeps its mandated brand colours and stays decorative', (name) => {
    const Icon = (authIcons as Record<string, unknown>)[name] as IconComponent;
    const { container } = render(<Icon />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    // A filled brand mark, not a stroke icon: it must NOT inherit the surrounding colour,
    // or the "Sign in with Google" button would render a monochrome imitation of the mark.
    expect(container.innerHTML).not.toContain('currentColor');
    expect(container.innerHTML).toMatch(/fill="#[0-9a-fA-F]{6}"/);
  });

  it('lets an icon be the accessible name when it is the only content', () => {
    // `IconButton` relies on this: props pass through, so a caller can un-hide the glyph
    // and name it rather than being stuck with a decorative-only icon.
    const { container } = render(<consoleIcons.BellIcon aria-hidden={false} aria-label="Alerts" />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('aria-hidden', 'false');
    expect(svg).toHaveAttribute('aria-label', 'Alerts');
  });
});
