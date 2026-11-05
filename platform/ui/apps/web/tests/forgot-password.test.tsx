import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ForgotPasswordForm } from '../src/components/ForgotPasswordForm';

describe('ForgotPasswordForm', () => {
  it('offers a way back to sign in and validates before submitting', async () => {
    const user = userEvent.setup();
    const requestReset = vi.fn();
    render(<ForgotPasswordForm requestReset={requestReset} />);
    expect(screen.getByRole('link', { name: /back to sign in/i })).toHaveAttribute('href', '/login');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByText('Enter your email address.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Email address'), 'not-an-address');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByText('That does not look like an email address.')).toBeInTheDocument();
    expect(requestReset).not.toHaveBeenCalled();
  });
  it('requests real recovery while keeping account existence private', async () => {
    const user = userEvent.setup();
    const requestReset = vi.fn(async () => ({ completed: true }));
    render(<ForgotPasswordForm requestReset={requestReset} />);
    await user.type(screen.getByLabelText('Email address'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(requestReset).toHaveBeenCalledWith('ada@example.com');
    expect(await screen.findByRole('status')).toHaveTextContent('If this address belongs to an eligible account');
  });
  it('recovers from transport errors without claiming email delivery', async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordForm requestReset={vi.fn(async () => { throw new Error('offline'); })} />);
    await user.type(screen.getByLabelText('Email address'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect');
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeEnabled();
    expect(screen.queryByText('Request received')).not.toBeInTheDocument();
  });
});
