/**
 * Every `pms-` class a component emits must be styled, or explicitly declared as an
 * unstyled structural hook.
 *
 * This exists because the component tests run with `css: false` — they assert structure and
 * behaviour, and would happily pass with a misspelt class name that renders unstyled in the
 * browser. That is the one class of UI defect the rest of the suite cannot see, and a
 * hand-authored design system with 170-odd class names will hit it eventually.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(__dirname, '..', 'src');
const STYLES = join(SRC, 'styles');
const COMPONENTS = join(SRC, 'components');

/**
 * Classes that intentionally carry no rule of their own. Each is a BEM element kept for
 * readable markup, or a hook on a component that inherits its styling from the primitive it
 * composes. Adding to this list should feel like a decision, which is the point.
 */
const UNSTYLED_HOOKS = new Set([
  // `NotificationBell` and `CollapseToggle` are `IconButton`s — `pms-btn--icon` styles them.
  'pms-bell',
  'pms-collapse',
  'pms-collapse--collapsed',
  // The `<li>` wrapper; its list already sets `list-style: none` and the spacing.
  'pms-rail-item-slot',
  // BEM elements whose parent rule positions them, with nothing of their own to set.
  'pms-disclosure__label',
  'pms-stat__label-text',
]);

function definedClasses(): Set<string> {
  const defined = new Set<string>();
  for (const file of readdirSync(STYLES).filter((f) => f.endsWith('.css'))) {
    const css = readFileSync(join(STYLES, file), 'utf8');
    for (const match of css.matchAll(/\.(pms-[A-Za-z0-9_-]+)/g)) {
      defined.add(match[1] as string);
    }
  }
  return defined;
}

/**
 * Class names appearing in a `className` value. Deliberately crude — it also picks up
 * template-literal fragments like `pms-btn--` from `` `pms-btn--${variant}` ``, which is
 * why a prefix match counts as defined below.
 */
function usedClasses(): Map<string, string> {
  const used = new Map<string, string>();
  for (const file of readdirSync(COMPONENTS).filter((f) => f.endsWith('.tsx'))) {
    const source = readFileSync(join(COMPONENTS, file), 'utf8');
    for (const match of source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{'([^']*)'\})/g)) {
      const chunk = match[1] ?? match[2] ?? match[3] ?? '';
      for (const token of chunk.matchAll(/pms-[A-Za-z0-9_-]+/g)) {
        if (!used.has(token[0])) used.set(token[0], file);
      }
    }
    // Class lists assembled in an array before joining — the house pattern for variants.
    for (const match of source.matchAll(/'(pms-[A-Za-z0-9_-]*)'/g)) {
      if (!used.has(match[1] as string)) used.set(match[1] as string, file);
    }
  }
  return used;
}

describe('class coverage', () => {
  it('styles every class the components emit', () => {
    const defined = definedClasses();
    const orphans: string[] = [];

    for (const [cls, file] of usedClasses()) {
      if (defined.has(cls)) continue;
      if (UNSTYLED_HOOKS.has(cls)) continue;
      // A template-literal prefix (`pms-badge--` + variant) counts when some rule extends it.
      if ([...defined].some((d) => d.startsWith(cls))) continue;
      orphans.push(`${cls} (${file})`);
    }

    expect(orphans).toEqual([]);
  });

  it('keeps the unstyled-hook list honest — an entry that gains a rule must leave the list', () => {
    const defined = definedClasses();
    const stale = [...UNSTYLED_HOOKS].filter((cls) => defined.has(cls));
    expect(stale).toEqual([]);
  });
});
