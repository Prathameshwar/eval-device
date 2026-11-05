import { act, fireEvent, within } from '@testing-library/react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../src/components/ThemeProvider';
import { ThemeSwitcher } from '../src/components/ThemeSwitcher';
import { ToastProvider, useToast } from '../src/components/Toast';
import { THEME_COOKIE, THEME_STORAGE_KEY } from '../src/lib/theme';

declare function __setPrefersDark(value: boolean): void;

function Trigger() {
  const toast = useToast();
  return <button onClick={() => toast.info('Hydrated notification')}>Notify</button>;
}

describe('server hydration', () => {
  it.each(['light', 'dark', 'ledger', 'system'] as const)(
    'hydrates saved %s theme and the toast portal without replacing server markup',
    async (preference) => {
      const tree = <ThemeProvider><ThemeSwitcher /><ToastProvider><Trigger /></ToastProvider></ThemeProvider>;
      const container = document.createElement('div');
      container.innerHTML = renderToString(tree);
      const serverButton = within(container).getByRole('button', { name: 'Notify' });
      // These browser values are unavailable to the server render.
      localStorage.setItem(THEME_STORAGE_KEY, preference);
      document.cookie = `${THEME_COOKIE}=${preference}; path=/`;
      __setPrefersDark(true);
      document.documentElement.setAttribute('data-theme', preference === 'system' ? 'dark' : preference);
      document.body.append(container);
      const recoverable = vi.fn();
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
      let root: Root | undefined;
      try {
        await act(async () => { root = hydrateRoot(container, tree, { onRecoverableError: recoverable }); });
        expect(within(container).getByRole('button', { name: 'Notify' })).toBe(serverButton);
        expect(within(container).getByRole('radio', { name: new RegExp(`^${preference}$`, 'i') }))
          .toHaveAttribute('aria-checked', 'true');
        expect(document.documentElement.getAttribute('data-theme')).toBe(preference === 'system' ? 'dark' : preference);
        expect(recoverable).not.toHaveBeenCalled();
        expect(consoleError).not.toHaveBeenCalled();
        fireEvent.click(serverButton);
        expect(within(document.body).getByText('Hydrated notification')).toBeInTheDocument();
      } finally {
        await act(async () => root?.unmount());
        consoleError.mockRestore();
        container.remove();
      }
    },
  );
});
