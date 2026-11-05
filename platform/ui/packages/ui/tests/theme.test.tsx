/**
 * `ThemeProvider` + `ThemeSwitcher`.
 *
 * The two behaviours worth the most here are the ones a manual pass never catches: an OS
 * theme flip repainting live while on `system`, and the subscription actually going away
 * when it shouldn't fire any more.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ThemeProvider, useTheme } from '../src/components/ThemeProvider';
import { ThemeSwitcher } from '../src/components/ThemeSwitcher';
import {
  THEME_COOKIE,
  THEME_PREFERENCES,
  THEME_STORAGE_KEY,
  colorSchemeFor,
  resolveTheme,
  type ThemePreference,
} from '../src/lib/theme';

declare function __setPrefersDark(value: boolean): void;
declare function __emitPrefersDark(value: boolean): void;

function themeAttr(): string | null {
  return document.documentElement.getAttribute('data-theme');
}

function colorScheme(): string {
  return document.documentElement.style.getPropertyValue('color-scheme');
}

/** Surfaces the context so the provider can be asserted without a switcher in the way. */
function Probe() {
  const { preference, resolved } = useTheme();
  return (
    <output>
      {preference}/{resolved}
    </output>
  );
}

describe('ThemeProvider', () => {
  it('renders its children', () => {
    render(
      <ThemeProvider>
        <p>console</p>
      </ThemeProvider>,
    );
    expect(screen.getByText('console')).toBeInTheDocument();
  });

  it('defaults to system when nothing is stored and no session preference is given', async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('system/light'));
  });

  it.each(THEME_PREFERENCES)('applies the palette %s resolves to', async (preference) => {
    __setPrefersDark(false);
    render(
      <ThemeProvider initial={preference}>
        <Probe />
      </ThemeProvider>,
    );
    const expected = resolveTheme(preference, false);
    await waitFor(() => expect(themeAttr()).toBe(expected));
    expect(colorScheme()).toBe(colorSchemeFor(expected));
    expect(screen.getByRole('status')).toHaveTextContent(`${preference}/${expected}`);
  });

  it('resolves an initial system against a dark OS', async () => {
    __setPrefersDark(true);
    render(
      <ThemeProvider initial="system">
        <Probe />
      </ThemeProvider>,
    );
    await waitFor(() => expect(themeAttr()).toBe('dark'));
    expect(colorScheme()).toBe('dark');
  });

  it('hydrates from the cookie when no session preference is supplied', async () => {
    document.cookie = `${THEME_COOKIE}=ledger; path=/`;
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    await waitFor(() => expect(themeAttr()).toBe('ledger'));
  });

  it('lets an explicit session preference outrank the cookie', async () => {
    document.cookie = `${THEME_COOKIE}=ledger; path=/`;
    render(
      <ThemeProvider initial="dark">
        <Probe />
      </ThemeProvider>,
    );
    await waitFor(() => expect(themeAttr()).toBe('dark'));
  });

  it('persists to both stores and reports the change so the app can PATCH the user', async () => {
    const onChange = vi.fn();
    render(
      <ThemeProvider initial="light" onChange={onChange}>
        <ThemeSwitcher />
      </ThemeProvider>,
    );

    await userEvent.click(screen.getByRole('radio', { name: 'Ledger' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('ledger');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('ledger');
    expect(document.cookie).toContain(`${THEME_COOKIE}=ledger`);
    expect(themeAttr()).toBe('ledger');
  });

  it('never stores the resolved value for a system user — that would freeze the OS out', async () => {
    __setPrefersDark(true);
    render(
      <ThemeProvider initial="light">
        <ThemeSwitcher />
      </ThemeProvider>,
    );

    await userEvent.click(screen.getByRole('radio', { name: 'System' }));

    await waitFor(() => expect(themeAttr()).toBe('dark'));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system');
  });

  it('repaints live when the OS flips while the preference is system', async () => {
    render(
      <ThemeProvider initial="system">
        <Probe />
      </ThemeProvider>,
    );
    await waitFor(() => expect(themeAttr()).toBe('light'));

    await act(async () => __emitPrefersDark(true));

    await waitFor(() => expect(themeAttr()).toBe('dark'));
    expect(colorScheme()).toBe('dark');
    expect(screen.getByRole('status')).toHaveTextContent('system/dark');
  });

  it('unsubscribes once the preference leaves system, so a later OS flip is ignored', async () => {
    render(
      <ThemeProvider initial="system">
        <ThemeSwitcher />
      </ThemeProvider>,
    );
    await waitFor(() => expect(themeAttr()).toBe('light'));

    await userEvent.click(screen.getByRole('radio', { name: 'Ledger' }));
    await waitFor(() => expect(themeAttr()).toBe('ledger'));

    await act(async () => __emitPrefersDark(true));

    // A dark OS must not drag an explicitly chosen palette away from the user.
    await waitFor(() => expect(themeAttr()).toBe('ledger'));
  });

  it('works without an onChange handler', async () => {
    render(
      <ThemeProvider initial="light">
        <ThemeSwitcher />
      </ThemeProvider>,
    );
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    await waitFor(() => expect(themeAttr()).toBe('dark'));
  });
});

describe('useTheme outside a provider', () => {
  it('throws an error that names the fix', () => {
    // React logs the boundary-less throw; the assertion is on the message, not the noise.
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      expect(() => render(<Probe />)).toThrow(/ThemeProvider/);
    } finally {
      error.mockRestore();
    }
  });
});

describe('ThemeSwitcher', () => {
  function setup(initial: ThemePreference = 'light') {
    render(
      <ThemeProvider initial={initial}>
        <ThemeSwitcher />
      </ThemeProvider>,
    );
    return screen.getAllByRole('radio');
  }

  it('renders one named radio per preference, in the catalogue order', () => {
    const radios = setup();
    expect(radios.map((radio) => radio.getAttribute('aria-label'))).toEqual([
      'Light',
      'Dark',
      'Ledger',
      'System',
    ]);
    // The icon is the only visible content, so the name must also be the hover tooltip.
    expect(radios.map((radio) => radio.getAttribute('title'))).toEqual([
      'Light',
      'Dark',
      'Ledger',
      'System',
    ]);
  });

  it('is a radiogroup with an accessible name', () => {
    setup();
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument();
  });

  it('marks only the current preference as checked', () => {
    const radios = setup('ledger');
    expect(radios.map((radio) => radio.getAttribute('aria-checked'))).toEqual([
      'false',
      'false',
      'true',
      'false',
    ]);
  });

  it('makes only the selected option a tab stop — the group is one stop, not four', async () => {
    const radios = setup('dark');
    expect(radios.map((radio) => radio.tabIndex)).toEqual([-1, 0, -1, -1]);

    await userEvent.click(screen.getByRole('radio', { name: 'System' }));
    expect(screen.getAllByRole('radio').map((radio) => radio.tabIndex)).toEqual([-1, -1, -1, 0]);
  });

  it('selects on click and moves aria-checked with it', async () => {
    setup('light');
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'false');
  });

  it.each([
    ['{ArrowRight}', 'Dark'],
    ['{ArrowDown}', 'Dark'],
    ['{ArrowLeft}', 'System'],
    ['{ArrowUp}', 'System'],
    ['{End}', 'System'],
    ['{Home}', 'Light'],
  ])('%s from Light selects and focuses %s', async (key, expected) => {
    setup('light');
    const first = screen.getByRole('radio', { name: 'Light' });
    first.focus();

    await userEvent.keyboard(key);

    const target = screen.getByRole('radio', { name: expected });
    expect(target).toHaveAttribute('aria-checked', 'true');
    expect(target).toHaveFocus();
  });

  it('wraps forwards off the last option', async () => {
    setup('system');
    screen.getByRole('radio', { name: 'System' }).focus();

    await userEvent.keyboard('{ArrowRight}');

    expect(screen.getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'true');
    expect(themeAttr()).toBe('light');
  });

  it('ignores keys it does not own, leaving the selection alone', async () => {
    setup('light');
    screen.getByRole('radio', { name: 'Light' }).focus();

    await userEvent.keyboard('{Escape}x');

    expect(screen.getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'true');
  });

  it('accepts a caller-supplied group label for a context that needs a longer name', () => {
    render(
      <ThemeProvider initial="light">
        <ThemeSwitcher label="Colour theme" />
      </ThemeProvider>,
    );
    expect(screen.getByRole('radiogroup', { name: 'Colour theme' })).toBeInTheDocument();
  });
});
