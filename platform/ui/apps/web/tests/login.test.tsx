import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LoginForm } from '../src/components/LoginForm';
import { DEMO_USERS } from './fixtures/accounts';

/**
 * The sign-in screen: fields labelled and typed correctly, local errors produced before anything
 * is sent, and the server's refusal shown without saying which half of the credentials was wrong.
 *
 * `signIn` is injected. The real one is a server action reaching for `cookies()`, which does not
 * exist in jsdom — and a test that mocked the module would be asserting against the mock rather
 * than against the seam the component actually uses.
 */

/** Stands in for the action: resolves with an error, or resolves having "navigated". */
function fakeSignIn(result?: { error: string }) {
  return vi.fn(async () => result);
}

function emailInput(): HTMLInputElement {
  return screen.getByLabelText('Email address') as HTMLInputElement;
}

function passwordInput(): HTMLInputElement {
  return screen.getByLabelText('Password') as HTMLInputElement;
}

describe('LoginForm', () => {
  it('renders the heading, both fields and the reset link', () => {
    render(<LoginForm />);

    expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(emailInput()).toHaveAttribute('type', 'email');
    expect(emailInput()).toHaveAttribute('autocomplete', 'email');
    expect(passwordInput()).toHaveAttribute('type', 'password');
    expect(passwordInput()).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute(
      'href',
      '/forgot-password',
    );
  });

  it('reports both missing fields on an empty submit and sends nothing', async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Enter your email address.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    expect(emailInput()).toHaveAttribute('aria-invalid', 'true');
    /* No pending state: a failed local check must not look like a request. */
    expect(screen.queryByText('Signing in…')).not.toBeInTheDocument();
  });

  it('rejects a malformed address and clears the error on the next keystroke', async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(emailInput(), 'ada@example');
    await user.type(passwordInput(), 'correct horse battery');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(
      await screen.findByText('That does not look like an email address.'),
    ).toBeInTheDocument();

    await user.type(emailInput(), '.com');
    expect(
      screen.queryByText('That does not look like an email address.'),
    ).not.toBeInTheDocument();
  });

  it('sends the credentials once the local checks pass, and shows a pending state', async () => {
    const user = userEvent.setup();
    const signIn = fakeSignIn();
    render(<LoginForm signIn={signIn} />);

    await user.type(emailInput(), 'ada@example.com');
    await user.type(passwordInput(), 'correct horse battery');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(signIn).toHaveBeenCalledWith('ada@example.com', 'correct horse battery', false);
    /* Success navigates, so the button stays in its pending state rather than flicking back for
     * the frame before the console renders. */
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled(),
    );
  });

  it('shows the refusal without saying which half of the credentials was wrong', async () => {
    const user = userEvent.setup();
    const signIn = fakeSignIn({
      error: 'That email address and password do not match an account.',
    });
    render(<LoginForm signIn={signIn} />);

    await user.type(emailInput(), DEMO_USERS[0]!.email);
    await user.type(passwordInput(), 'not the password');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    const notice = await screen.findByRole('alert');
    expect(notice).toHaveTextContent('Sign-in failed');
    expect(notice).toHaveTextContent(/do not match an account/i);
    /* Which of the two was wrong is information about who holds an account here. */
    expect(notice).not.toHaveTextContent(/no such|unknown user|wrong password/i);
    /* The form comes back, rather than staying stuck in its pending state. */
    await waitFor(() => expect(screen.getByRole('button', { name: /^Sign in/ })).toBeEnabled());
  });

  it('does not reach the server until the local checks pass', async () => {
    const user = userEvent.setup();
    const signIn = fakeSignIn();
    render(<LoginForm signIn={signIn} />);

    await user.type(emailInput(), 'ada@example');
    await user.type(passwordInput(), 'something');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(signIn).not.toHaveBeenCalled();
  });

  /*
   * The demo picker fills the address only. The password is deliberately not in this bundle —
   * `tests/demo-session.test.ts` holds that property — so it cannot be filled from here.
   */
  it('unmasks the password on demand without losing the value', async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(passwordInput(), 'correct horse');
    await user.click(screen.getByRole('button', { name: 'Show password' }));

    expect(passwordInput()).toHaveAttribute('type', 'text');
    expect(passwordInput()).toHaveValue('correct horse');
    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(passwordInput()).toHaveAttribute('type', 'password');
  });

  it('leaves "keep me signed in" off until it is chosen, and then sends it', async () => {
    const user = userEvent.setup();
    const signIn = fakeSignIn();
    render(<LoginForm signIn={signIn} />);

    const box = screen.getByRole('checkbox', { name: 'Keep me signed in' });
    expect(box).not.toBeChecked();
    await user.click(box);
    expect(box).toBeChecked();

    /* The checkbox has to reach the server or it is furniture: it is the difference between a
     * session that lasts a working day and one that lasts a month. */
    await user.type(emailInput(), 'ada@example.com');
    await user.type(passwordInput(), 'correct horse battery');
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    expect(signIn).toHaveBeenCalledWith('ada@example.com', 'correct horse battery', true);
  });
  it('recovers from a rejected sign-in request and permits retry', async () => {
    const user = userEvent.setup();
    const signIn = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ error: 'Try again.' });
    render(<LoginForm signIn={signIn} />);
    await user.type(emailInput(), 'ada@example.com');
    await user.type(passwordInput(), 'a test password long enough');
    await user.click(screen.getByRole('button', { name: /^Sign in/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect');
    expect(screen.getByRole('button', { name: /^Sign in/ })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: /^Sign in/ }));
    expect(signIn).toHaveBeenCalledTimes(2);
  });

  it('offers a full refresh for an obsolete deployment without replaying credentials', async () => {
    const user = userEvent.setup();
    const error = new Error('Server Action was not found');
    error.name = 'UnrecognizedActionError';
    const signIn = vi.fn().mockRejectedValue(error);
    render(<LoginForm signIn={signIn} />);
    await user.type(emailInput(), 'ada@example.com');
    await user.type(passwordInput(), 'a test password long enough');
    await user.click(screen.getByRole('button', { name: /^Sign in/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The platform was updated');
    expect(screen.getByRole('button', { name: 'Refresh page' })).toBeEnabled();
    expect(passwordInput()).toHaveValue('');
    expect(screen.getByRole('button', { name: /^Sign in/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /^Sign in/ }));
    expect(signIn).toHaveBeenCalledTimes(1);
  });
});
