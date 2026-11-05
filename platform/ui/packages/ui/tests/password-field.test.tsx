/**
 * `PasswordField`.
 *
 * `tests/primitives.test.tsx` already covers the toggle and that the meter appears only when asked
 * for. This file is the rest: the scoring rules one at a time, the two things a masked field hides
 * from its user (Caps Lock, and their own typo), and the attributes that decide whether a password
 * manager offers to generate a password or silently autofills the old one.
 *
 * The scoring tests are the valuable half. A strength meter that calls `12345678` "Fair" is worse
 * than no meter, because it is advice that is confidently wrong.
 */
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PasswordField, assessPassword, scorePassword } from '../src/components/PasswordField';

function field(name = 'Password'): HTMLInputElement {
  return screen.getByLabelText(name) as HTMLInputElement;
}

/** Holds the value, so typing behaves the way it does in a form. */
function Harness(props: Partial<React.ComponentProps<typeof PasswordField>>) {
  const [value, setValue] = useState('');
  return (
    <PasswordField
      label="Password"
      {...props}
      value={value}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}

describe('assessPassword — length', () => {
  it.each([
    ['', 0],
    ['short', 0],
    ['Abcdef1', 0],
  ])('scores %j as 0 — nothing else is considered until it is 8 long', (value, expected) => {
    expect(assessPassword(value).score).toBe(expected);
    expect(assessPassword(value).label).toBe('Too short');
  });

  it('says what is missing while it is too short', () => {
    expect(assessPassword('abc').advice).toBe('Add 8+ characters, a number, a symbol');
  });

  it('rewards a long passphrase over a short password that ticks every box', () => {
    // The strongest thing most people will actually type must not score below `P@ss1x!`.
    const passphrase = assessPassword('correct horse battery staple');
    expect(passphrase.score).toBe(3);
    expect(passphrase.label).toBe('Good');
  });

  it('gives the bonus at 16 characters, not before', () => {
    expect(assessPassword('abcxyzabcxyzabc').score).toBe(1); // 15
    expect(assessPassword('abcxyzabcxyzabcx').score).toBe(2); // 16
  });
});

describe('assessPassword — character classes', () => {
  it.each([
    ['abcxyzqp', 1, 'Weak'],
    ['Abcxyzqp', 2, 'Fair'],
    ['Abcxyzq1', 3, 'Good'],
    ['Abcxyzq1!', 4, 'Strong'],
  ])('scores %j as %i (%s)', (value, score, label) => {
    expect(assessPassword(value)).toMatchObject({ score, label });
  });

  it('caps at 4 when every rule fires', () => {
    expect(assessPassword('Abcxyzq1!Abcxyzq1!').score).toBe(4);
  });

  it('needs both cases for the mixed-case point', () => {
    expect(assessPassword('ABCXYZQP').score).toBe(1);
  });

  it('counts a space as a symbol, because it is one', () => {
    expect(assessPassword('abc xyzq').score).toBe(2);
  });

  it('advises only what is missing', () => {
    expect(assessPassword('Abcxyzqp').advice).toBe('Add a number, a symbol');
    expect(assessPassword('Abcxyzq1!').advice).toBe('Looks strong');
  });
});

describe('assessPassword — the sequences that get guessed first', () => {
  it.each([
    ['12345678', 'a run of digits'],
    ['abcdefgh', 'a run of letters'],
    ['87654321', 'a run backwards'],
    ['aaaaaaaa', 'one character repeated'],
    ['11111111', 'one digit repeated'],
  ])('caps %j at 1 (%s)', (value) => {
    // `12345678` would otherwise score 2 for having digits — advice that is confidently wrong.
    const assessment = assessPassword(value);
    expect(assessment.score).toBe(1);
    expect(assessment.label).toBe('Weak');
    expect(assessment.advice).toBe('A single repeated character or a run like this is guessed first');
  });

  it('does not punish the shift key', () => {
    // `Abcdefgh` is a capital followed by a run, not a run. Comparing case-insensitively here
    // would score it below `abcdefgh`'s sibling that used no shift at all.
    expect(assessPassword('Abcdefgh').score).toBe(2);
  });

  it('leaves a password that merely contains a short run alone', () => {
    expect(assessPassword('Qabc9!xz').score).toBe(4);
  });
});

describe('assessPassword — reuse of what is on the form', () => {
  it('refuses a password containing the email address', () => {
    const assessment = assessPassword('ada@example.com1!', ['ada@example.com']);

    expect(assessment.score).toBe(0);
    expect(assessment.label).toBe('Too guessable');
    expect(assessment.advice).toBe('Avoid your name, email address or anything else on this form');
  });

  it('matches case-insensitively and ignores surrounding space', () => {
    expect(assessPassword('xLovelace99!', [' lovelace ']).score).toBe(0);
  });

  it('ignores a token too short to mean anything', () => {
    // An initial, or a `.com`, would otherwise condemn every password on the form.
    expect(assessPassword('Abcxyzq1!', ['A', 'de']).score).toBe(4);
  });

  it('says nothing when there is nothing to avoid', () => {
    expect(assessPassword('Abcxyzq1!', ['bertrand@example.com']).score).toBe(4);
  });
});

describe('scorePassword', () => {
  it('is the score from the same assessment, so the meter and a submit guard cannot disagree', () => {
    for (const value of ['', 'short', 'abcxyzqp', 'Abcxyzq1!', 'correct horse battery staple']) {
      expect(scorePassword(value)).toBe(assessPassword(value).score);
    }
  });
});

describe('PasswordField — purpose', () => {
  it('asks a password manager to fill the existing password by default', () => {
    render(<PasswordField label="Password" value="" onChange={vi.fn()} />);
    expect(field()).toHaveAttribute('autocomplete', 'current-password');
  });

  it('asks it to generate a new one when that is what this is', () => {
    // The difference between a suggested strong password and a silent autofill of the old one.
    render(<PasswordField label="New password" value="" onChange={vi.fn()} purpose="new" />);
    expect(field('New password')).toHaveAttribute('autocomplete', 'new-password');
  });

  it('shows the meter for a new password without being asked', () => {
    render(<PasswordField label="New password" value="Abcxyzq1!" onChange={vi.fn()} purpose="new" />);
    expect(screen.getByText('Strong')).toBeInTheDocument();
  });

  it('keeps the meter off a sign-in field, where strength advice is useless', () => {
    render(<PasswordField label="Password" value="Abcxyzq1!" onChange={vi.fn()} />);
    expect(screen.queryByText('Strong')).not.toBeInTheDocument();
  });

  it('lets the caller override either default', () => {
    const { rerender } = render(
      <PasswordField label="Password" value="Abcxyzq1!" onChange={vi.fn()} showStrength />,
    );
    expect(screen.getByText('Strong')).toBeInTheDocument();

    rerender(
      <PasswordField
        label="New password"
        value="Abcxyzq1!"
        onChange={vi.fn()}
        purpose="new"
        showStrength={false}
        autoComplete="off"
      />,
    );
    expect(screen.queryByText('Strong')).not.toBeInTheDocument();
    expect(field('New password')).toHaveAttribute('autocomplete', 'off');
  });

  it('never lets the platform rewrite what was typed', () => {
    render(<PasswordField label="Password" value="" onChange={vi.fn()} />);
    const input = field();

    // A spellcheck would send the password to the platform's dictionary service; autocorrect and
    // autocapitalise would change it.
    expect(input).toHaveAttribute('spellcheck', 'false');
    expect(input).toHaveAttribute('autocapitalize', 'none');
    expect(input).toHaveAttribute('autocorrect', 'off');
  });
});

describe('PasswordField — the meter', () => {
  it('names the score on the wrapper, which is what colours the bars', () => {
    const { container, rerender } = render(
      <PasswordField label="Password" value="abcxyzqp" onChange={vi.fn()} showStrength />,
    );
    expect(container.querySelector('.pms-strength')).toHaveAttribute('data-score', '1');

    rerender(<PasswordField label="Password" value="Abcxyzq1!" onChange={vi.fn()} showStrength />);
    expect(container.querySelector('.pms-strength')).toHaveAttribute('data-score', '4');
  });

  it('hides the bars from the accessibility tree and announces the words instead', () => {
    const { container } = render(
      <PasswordField label="Password" value="Abcxyzq1!" onChange={vi.fn()} showStrength />,
    );

    // Four empty spans announce nothing; the line beside them carries the whole meaning.
    expect(container.querySelector('.pms-strength__track')).toHaveAttribute('aria-hidden', 'true');
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Strong');
    expect(status).toHaveTextContent('Looks strong');
  });

  it('passes the avoid list through to the meter', async () => {
    const user = userEvent.setup();
    render(<Harness purpose="new" avoid={['ada@example.com']} />);

    await user.type(field(), 'ada@example.com');

    expect(screen.getByText('Too guessable')).toBeInTheDocument();
  });
});

describe('PasswordField — Caps Lock', () => {
  it('warns while the key is on and the password is masked', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(field());
    // The state is read from the event, not tracked as a key press: Caps Lock may have been on
    // before this field ever had focus.
    await user.keyboard('{CapsLock}');

    expect(screen.getByText('Caps Lock is on')).toBeInTheDocument();
  });

  it('stops warning when the key goes off', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(field());
    await user.keyboard('{CapsLock}');
    // Then carry on typing, which is what actually happens. `user-event` reports the *old* lock
    // state on the toggling key's own keyup — a real browser reports the new one — so the next
    // real key press is where this can be observed here.
    await user.keyboard('{CapsLock}a');

    expect(screen.queryByText('Caps Lock is on')).not.toBeInTheDocument();
  });

  it('says nothing once the characters are on screen', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(field());
    await user.keyboard('{CapsLock}');
    await user.click(screen.getByRole('button', { name: 'Show password' }));

    // With the password visible, Caps Lock is something the user can see for themselves.
    expect(screen.queryByText('Caps Lock is on')).not.toBeInTheDocument();
  });

  it('says nothing about a field nobody is typing into', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Harness />
        <button type="button">Elsewhere</button>
      </>,
    );

    await user.click(field());
    await user.keyboard('{CapsLock}');
    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));

    expect(screen.queryByText('Caps Lock is on')).not.toBeInTheDocument();
  });

  it("does not swallow the caller's own key and focus handlers", async () => {
    const onKeyDown = vi.fn();
    const onFocus = vi.fn();
    const onBlur = vi.fn();
    const user = userEvent.setup();
    render(<Harness onKeyDown={onKeyDown} onFocus={onFocus} onBlur={onBlur} />);

    await user.click(field());
    await user.keyboard('a');
    await user.tab();

    expect(onFocus).toHaveBeenCalledTimes(1);
    // `a`, then the Tab that leaves the field — Tab is a key press too.
    expect(onKeyDown).toHaveBeenCalledTimes(2);
    expect(onBlur).toHaveBeenCalledTimes(1);
  });
});

describe('PasswordField — the toggle', () => {
  it('names the field it belongs to, keeping its visible word inside the name', () => {
    render(<PasswordField label="New password" value="x" onChange={vi.fn()} />);
    const toggle = screen.getByRole('button', { name: 'Show new password' });

    // WCAG 2.5.3: speech control must still be able to say "Show".
    expect(toggle).toHaveTextContent('Show');
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });

  it('reports itself as pressed while the password is showing', async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" value="x" onChange={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Show password' }));

    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('never blocks a paste', async () => {
    // Blocking paste defeats password managers, which buys a theoretical shoulder-surfing win for
    // the certainty of weaker, reused, hand-typed passwords.
    const user = userEvent.setup();
    render(<Harness purpose="new" />);

    await user.click(field());
    await user.paste('Xw7!qmz4Rb2#tuvo');

    expect(field().value).toBe('Xw7!qmz4Rb2#tuvo');
    expect(screen.getByText('Strong')).toBeInTheDocument();
  });
});
