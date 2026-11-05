import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The stylesheet checks the component tests cannot make.
 *
 * Tests here run with `css: false`, exactly as `@pms/ui`'s do, so a misspelt class name renders
 * unstyled and every assertion still passes. The package guards against that with
 * `tests/class-coverage.test.ts`; this is the same guard for the app's three stylesheets, plus
 * the two rules that keep these screens theme-safe:
 *
 *   - **No colour literal.** One hex in `auth.css` is a panel that stays light-indigo when the
 *     user picks the dark palette. Colour belongs to `theme-*.css` and reaches these files only
 *     through `--pms-*`.
 *   - **No `z-index`.** The package declares the whole stacking order in `tokens.css`; an app
 *     inventing its own number is how a decorative wash ends up over a focus ring.
 *
 * Comments are stripped everywhere before matching, because these files explain themselves by
 * naming the very classes and tokens they are about.
 */

const APP = join(__dirname, '..', 'src');
const APP_STYLES = join(APP, 'styles');
/* Reached through the workspace link on purpose: if the package moves, this fails loudly rather
 * than quietly checking the app against an empty set of classes. */
const PACKAGE_STYLES = join(__dirname, '..', '..', '..', 'packages', 'ui', 'src', 'styles');

/**
 * The classes this app owns. A rule keyed off a *package* class — `.pms-shell[data-collapsed]`,
 * say, which the console uses to hide the sign-out label — is a legitimate consumer override, and
 * the app's own source never spells that class. So the unused-rule check considers only these
 * prefixes; the undefined-class check below still considers every class the app emits.
 */
const OWNED = /^pms-(auth|brand|console)\b/;

/** Block comments, JSX comment wrappers, and whole-line `//` or ` *` comments. */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
    .replace(/^[ \t]*\*.*$/gm, '');
}

function read(file: string): string {
  return stripComments(readFileSync(file, 'utf8'));
}

function cssFilesIn(directory: string): string[] {
  return readdirSync(directory)
    .filter((name) => name.endsWith('.css'))
    .map((name) => join(directory, name));
}

function classesIn(files: readonly string[]): Set<string> {
  const found = new Set<string>();
  for (const file of files) {
    for (const match of read(file).matchAll(/\.(pms-[A-Za-z0-9_-]+)/g)) {
      found.add(match[1] as string);
    }
  }
  return found;
}

function sourceFiles(directory: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) out.push(...sourceFiles(path));
    else if (/\.tsx?$/.test(entry)) out.push(path);
  }
  return out;
}

const APP_CSS = cssFilesIn(APP_STYLES);
const APP_SOURCE = sourceFiles(APP);
const APP_TEXT = APP_SOURCE.map(read).join('\n');

describe('app stylesheets', () => {
  it('has the application stylesheets it claims to have', () => {
    expect(APP_CSS.map((file) => file.replace(/.*[\\/]/, '')).sort()).toEqual([
      'auth.css',
      'brand.css',
      'console.css',
      'models.css',
    ]);
    expect(APP_SOURCE.length).toBeGreaterThan(10);
  });

  it('styles every class the app emits, here or in the design system', () => {
    const defined = new Set([...classesIn(APP_CSS), ...classesIn(cssFilesIn(PACKAGE_STYLES))]);
    /* `(?<!-)` drops a `--pms-*` custom property: those are tokens, not classes. */
    const used = new Set(APP_TEXT.match(/(?<!-)\bpms-[A-Za-z0-9_-]+/g) ?? []);

    expect([...used].filter((name) => !defined.has(name))).toEqual([]);
    /* A guard on the guard: if the regex ever stops matching, the assertion above passes vacuously. */
    expect(used.has('pms-auth__card')).toBe(true);
    expect(used.has('pms-console__signout')).toBe(true);
    expect(used.has('pms-h1')).toBe(true);
  });

  it('carries no rule of its own that nothing uses', () => {
    const orphans = [...classesIn(APP_CSS)]
      .filter((name) => OWNED.test(name))
      .filter((name) => !APP_TEXT.includes(name));
    expect(orphans).toEqual([]);
  });

  it('states no colour of its own', () => {
    for (const file of APP_CSS) {
      const rules = read(file);
      expect(rules, file).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(rules, file).not.toMatch(/\b(?:rgba?|hsla?|lab|oklch)\(/);
      /* `transparent` and `currentColor` are not palette colours; a named hue is. */
      expect(rules, file).not.toMatch(/:\s*(?:white|black|red|green|blue|grey|gray|indigo|navy)\b/i);
    }
  });

  it('invents no stacking order', () => {
    for (const file of APP_CSS) {
      expect(read(file), file).not.toMatch(/z-index/);
    }
  });
});
