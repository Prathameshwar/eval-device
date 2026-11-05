import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import type { ComponentType } from 'react';
import { describe, expect, it } from 'vitest';
import * as icons from '../src/components/icons-product';

/**
 * The same contract the package holds its own icons to: one `<svg>`, sized by the `size` prop,
 * decorative by default, and drawn only in `currentColor`.
 *
 * The colour rule is the one that matters. An icon with a literal fill reads correctly in the
 * light palette and then sits as a light-indigo smudge on the dark one — and because these are
 * used inside signal-toned tiles, it would also contradict the tone it is standing in.
 */

/* `ComponentType`, not the global `JSX` namespace: React 19's types no longer declare one
 * globally, so `JSX.Element` resolves to nothing under this tsconfig. */
const ENTRIES = Object.entries(icons) as [string, ComponentType<{ size?: number }>][];
const SOURCE = readFileSync(
  join(__dirname, '..', 'src', 'components', 'icons-product.tsx'),
  'utf8',
);

describe('product icons', () => {
  it('ships the six the design system has no equivalent for', () => {
    expect(ENTRIES.map(([name]) => name).sort()).toEqual([
      'DeviceIcon',
      'LicenseIcon',
      'ModelIcon',
      'PulseIcon',
      'SessionIcon',
      'TenantIcon',
    ]);
  });

  it.each(ENTRIES)('%s renders one decorative svg on a 24 grid', (_name, Icon) => {
    const { container } = render(<Icon />);
    const svgs = container.querySelectorAll('svg');

    expect(svgs).toHaveLength(1);
    const svg = svgs[0] as SVGElement;
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
    expect(svg).toHaveAttribute('fill', 'none');
    /* The package's default is 18; matching it means an app icon and a package icon sit at the
     * same size in the same rail row without either call site passing a number. */
    expect(svg).toHaveAttribute('width', '18');
  });

  it.each(ENTRIES)('%s takes its size from the caller', (_name, Icon) => {
    const { container } = render(<Icon size={28} />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('width', '28');
    expect(svg).toHaveAttribute('height', '28');
  });

  it('draws in currentColor only', () => {
    expect(SOURCE).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(SOURCE).not.toMatch(/\b(?:rgba?|hsla?)\(/);
    /* `stroke=` and `fill=` must resolve to the shared constant or to `none`. */
    for (const match of SOURCE.matchAll(/(?:stroke|fill)=(\{[^}]*\}|"[^"]*")/g)) {
      expect(['{S}', '"none"'], match[0]).toContain(match[1]);
    }
  });
});
