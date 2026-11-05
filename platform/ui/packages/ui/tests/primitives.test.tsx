/** Shared form primitives, tested independently of consuming applications. */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Button } from '../src/components/Button';
import { Checkbox } from '../src/components/Checkbox';
import { PasswordField, scorePassword } from '../src/components/PasswordField';
import { TextField } from '../src/components/TextField';
import { MailIcon } from '../src/components/icons';

describe('scorePassword', () => {
  it('scores by length then character variety', () => {
    expect(scorePassword('short')).toBe(0); // under 8 chars
    expect(scorePassword('abcdefgh')).toBe(1); // length only
    expect(scorePassword('Abcdefgh')).toBe(2); // + mixed case
    expect(scorePassword('Abcdefg1')).toBe(3); // + digit
    expect(scorePassword('Abcdefg1!')).toBe(4); // + symbol
  });
});

describe('Button', () => {
  it('shows a spinner, announces busy, and disables while loading', () => {
    render(
      <Button loading loadingLabel="Signing in…">
        Sign in
      </Button>,
    );
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
    expect(btn).toHaveTextContent('Signing in…');
    expect(btn).not.toHaveTextContent('Sign in');
  });
});

describe('TextField', () => {
  it('wires label to input via a generated id', () => {
    render(<TextField label="User ID" placeholder="x" />);
    expect(screen.getByLabelText('User ID')).toBeInTheDocument();
  });

  it('marks the input invalid and announces the error', () => {
    render(<TextField label="Email" error="Enter a valid email" />);
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Enter a valid email');
    expect(input.getAttribute('aria-describedby')).toContain(alert.id);
  });

  it('renders a leading icon decoratively and pads the input for it', () => {
    render(<TextField label="Work email" leading={<MailIcon size={18} />} />);
    const input = screen.getByLabelText('Work email');
    expect(input.className).toContain('pms-input--leading');
    // the icon is decorative — the label names the field, so it is hidden from AT
    const lead = document.querySelector('.pms-input__lead');
    expect(lead).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('PasswordField', () => {
  it('toggles between hidden and visible', async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" value="hunter2" onChange={() => {}} />);
    const input = screen.getByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');
    // The toggle's accessible name carries the field it belongs to — a create-account form has
    // two of these, and "Show / Show" says nothing about which. Its visible word is still `Show`.
    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');
    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
  });

  it('shows the strength meter only when asked and only with input', () => {
    const { rerender } = render(
      <PasswordField label="Password" value="" onChange={() => {}} showStrength />,
    );
    expect(screen.queryByText(/Add|strong/i)).not.toBeInTheDocument();
    rerender(<PasswordField label="Password" value="Abcdef1!" onChange={() => {}} showStrength />);
    expect(screen.getByText('Strong')).toBeInTheDocument();
  });
});

describe('Checkbox', () => {
  it('renders a real checkbox with its label', async () => {
    const user = userEvent.setup();
    render(<Checkbox>Keep me signed in</Checkbox>);
    const box = screen.getByRole('checkbox', { name: /keep me signed in/i });
    expect(box).not.toBeChecked();
    await user.click(box);
    expect(box).toBeChecked();
  });

  it('carries the mixed state, which HTML has no attribute for', () => {
    const { rerender } = render(<Checkbox indeterminate>Select all rows on this page</Checkbox>);
    const box = screen.getByRole('checkbox');

    // The DOM property, set through a ref — browsers expose it as `aria-checked="mixed"`.
    expect(box).toBePartiallyChecked();
    expect(box).not.toBeChecked();

    rerender(<Checkbox indeterminate={false}>Select all rows on this page</Checkbox>);
    // Kept in step with the prop, not only set on mount: the parent re-renders with every tick.
    expect(box).not.toBePartiallyChecked();
  });
});
