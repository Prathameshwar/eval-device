import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { InitialSetup } from '../src/components/InitialSetup';

async function installation(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Installation key'), 'a-private-installation-key');
  await user.click(screen.getByRole('button', { name: 'Verify installation' }));
}

async function administrator(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Full name'), 'Ada Admin');
  await user.type(screen.getByLabelText('Email address'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password', { exact: true }), 'my unique test passphrase');
  await user.type(screen.getByLabelText('Confirm password'), 'my unique test passphrase');
  await user.click(screen.getByRole('button', { name: 'Review details' }));
}

describe('Initial setup wizard', () => {
  it('validates each step, reviews without secrets, and creates once with a sign-in link', async () => {
    const user = userEvent.setup();
    const verify = vi.fn().mockResolvedValue({ completed: true });
    const complete = vi.fn().mockResolvedValue({ completed: true });
    render(<InitialSetup verifyKey={verify} complete={complete} />);
    expect(screen.queryByLabelText('Full name')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Verify installation' }));
    expect(verify).not.toHaveBeenCalled();
    expect(await screen.findByText('Enter your installation key.')).toBeInTheDocument();
    await installation(user);
    await user.click(screen.getByRole('button', { name: 'Review details' }));
    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
    expect(complete).not.toHaveBeenCalled();
    await administrator(user);
    expect(screen.getByRole('heading', { name: 'Review and finish' })).toHaveFocus();
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('my unique test passphrase')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('a-private-installation-key')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByLabelText('Full name')).toHaveValue('Ada Admin');
    await user.click(screen.getByRole('button', { name: 'Review details' }));
    await user.click(screen.getByRole('button', { name: 'Create administrator' }));
    expect(complete).toHaveBeenCalledTimes(1);
    expect(complete).toHaveBeenCalledWith({ display_name: 'Ada Admin', email: 'ada@example.com', password: 'my unique test passphrase', installation_key: 'a-private-installation-key' });
    expect(await screen.findByRole('heading', { name: 'Your platform is ready' })).toHaveFocus();
    expect(screen.getByRole('link', { name: 'Continue to sign in' })).toHaveAttribute('href', '/login');
    expect(localStorage.length).toBe(0);
  });

  it('handles a wrong key, lost connection, and concurrent completion', async () => {
    const user = userEvent.setup();
    const verify = vi.fn().mockResolvedValueOnce({ error: 'Incorrect key', code: 'invalid_setup_key' })
      .mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ code: 'setup_completed' });
    render(<InitialSetup verifyKey={verify} />);
    await installation(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect key');
    expect(screen.getByLabelText('Installation key')).toHaveValue('');
    await installation(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect');
    await user.click(screen.getByRole('button', { name: 'Verify installation' }));
    expect(await screen.findByRole('heading', { name: 'Setup is already complete' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Installation key')).not.toBeInTheDocument();
  });

  it('returns to administrator details when the API rejects a password', async () => {
    const user = userEvent.setup();
    render(<InitialSetup verifyKey={async () => ({ completed: true })}
      complete={async () => ({ error: 'Choose a less common password.', code: 'invalid_password' })} />);
    await installation(user);
    await administrator(user);
    await user.click(screen.getByRole('button', { name: 'Create administrator' }));
    expect(await screen.findByRole('heading', { name: 'Create your administrator' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a less common password.');
  });

  it('rejects mismatched confirmation and prevents duplicate verification requests', async () => {
    const user = userEvent.setup();
    let finish!: (value: { completed: boolean }) => void;
    const verify = vi.fn(() => new Promise<{ completed: boolean }>((resolve) => { finish = resolve; }));
    render(<InitialSetup verifyKey={verify} />);
    await installation(user);
    expect(screen.getByRole('button', { name: 'Verifying…' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Verifying…' }));
    expect(verify).toHaveBeenCalledTimes(1);
    finish({ completed: true });
    await screen.findByLabelText('Full name');
    await user.type(screen.getByLabelText('Password', { exact: true }), 'my private test passphrase');
    await user.type(screen.getByLabelText('Confirm password'), 'different passphrase');
    await user.click(screen.getByRole('button', { name: 'Review details' }));
    expect(screen.getByText('The passwords must match.')).toBeInTheDocument();
  });
});
