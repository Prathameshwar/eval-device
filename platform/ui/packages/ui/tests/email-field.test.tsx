/**
 * `EmailField`.
 *
 * Two things are worth testing here and they are not the obvious one. The obvious one — "does it
 * render an input" — is `TextField`'s job and is already covered. What is this control's own are
 * (a) the input attributes, because they are invisible, never noticed in review, and each one
 * fixes a real mobile-keyboard or autofill failure; and (b) the blur-time normalization, which is
 * the only place this control rewrites what the user typed and therefore the only place it can
 * lose data.
 *
 * The normalization cases are all real pastes: a mail client's `Name <addr>`, a copied `mailto:`
 * link, a spreadsheet cell with a trailing space, an address carrying a zero-width character from
 * a rich-text editor.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { EmailField, isEmailLike, normalizeEmail } from '../src/components/EmailField';

function field(name = 'Email'): HTMLInputElement {
  return screen.getByLabelText(name) as HTMLInputElement;
}

describe('normalizeEmail', () => {
  it.each([
    ['ada@example.com', 'ada@example.com'],
    // A trailing space from a spreadsheet cell, and a leading one from a chat paste.
    ['  ada@example.com ', 'ada@example.com'],
    // What a mail client puts on the clipboard.
    ['Ada Lovelace <ada@example.com>', 'ada@example.com'],
    ['<ada@example.com>', 'ada@example.com'],
    // A copied link.
    ['mailto:ada@example.com', 'ada@example.com'],
    ['MAILTO:ada@example.com', 'ada@example.com'],
    // A rich-text editor's zero-width space, and a bidi mark from a right-to-left document.
    ['ada\u200B@example.com', 'ada@example.com'],
    ['\u202Eada@example.com', 'ada@example.com'],
    // Interior whitespace is noise, not a separator — nobody means two addresses here.
    ['ada @ example.com', 'ada@example.com'],
  ])('tidies %j into %j', (raw, expected) => {
    expect(normalizeEmail(raw)).toBe(expected);
  });

  it('lowercases the domain, because domains are case-insensitive', () => {
    expect(normalizeEmail('ada@EXAMPLE.COM')).toBe('ada@example.com');
  });

  it('leaves the local part alone, because the RFC says it is case-sensitive', () => {
    // Rewriting this would silently change the mailbox on a server that honours the spec.
    expect(normalizeEmail('Ada.Lovelace@example.com')).toBe('Ada.Lovelace@example.com');
  });

  it('splits on the last @, so a local part containing one survives', () => {
    expect(normalizeEmail('"a@b"@Example.com')).toBe('"a@b"@example.com');
  });

  it('leaves a value with no @ untouched apart from the noise', () => {
    // Half-typed input must not be mangled into something else.
    expect(normalizeEmail(' ada ')).toBe('ada');
  });

  it('is idempotent — normalizing twice changes nothing', () => {
    const once = normalizeEmail('Ada Lovelace <Ada@EXAMPLE.com> ');
    expect(normalizeEmail(once)).toBe(once);
  });
});

describe('isEmailLike', () => {
  it.each([
    'ada@example.com',
    'ada+billing@example.co.in',
    'ada.lovelace@sub.example.com',
    "o'brien@example.ie",
    'ada@example.museum',
  ])('accepts %j', (value) => {
    expect(isEmailLike(value)).toBe(true);
  });

  it.each([
    ['', 'empty'],
    ['ada', 'no domain'],
    ['ada@', 'nothing after the @'],
    ['@example.com', 'nothing before the @'],
    ['ada@example', 'no dot in the domain'],
    ['ada@@example.com', 'two @s'],
    ['ada@example..com', 'an empty domain label'],
    ['ada @example.com', 'a space'],
    ['ada@example.com.', 'a trailing dot'],
  ])('rejects %j (%s)', (value) => {
    expect(isEmailLike(value)).toBe(false);
  });

  it('rejects an address longer than the column', () => {
    // `VARCHAR(320)` — accepting it here would defer the failure to the INSERT.
    const long = `${'a'.repeat(310)}@example.com`;
    expect(long.length).toBeGreaterThan(320);
    expect(isEmailLike(long)).toBe(false);
  });
});

describe('EmailField — the attributes nobody notices', () => {
  it('carries every attribute an email input needs', () => {
    render(<EmailField label="Email" value="" onChange={vi.fn()} />);
    const input = field();

    expect(input).toHaveAttribute('type', 'email');
    // The `@` on the first layer of a phone keyboard.
    expect(input).toHaveAttribute('inputmode', 'email');
    expect(input).toHaveAttribute('autocomplete', 'email');
    // iOS capitalises the first letter of a "sentence" otherwise.
    expect(input).toHaveAttribute('autocapitalize', 'none');
    expect(input).toHaveAttribute('autocorrect', 'off');
    expect(input).toHaveAttribute('spellcheck', 'false');
    // The column is VARCHAR(320).
    expect(input).toHaveAttribute('maxlength', '320');
  });

  it('shows the mail icon without announcing it — the label already names the field', () => {
    const { container } = render(<EmailField label="Email" value="" onChange={vi.fn()} />);
    const lead = container.querySelector('.pms-input__lead');

    expect(lead).not.toBeNull();
    expect(lead).toHaveAttribute('aria-hidden', 'true');
  });

  it('passes the field anatomy through — hint, error and the optional note', () => {
    const { rerender } = render(
      <EmailField
        label="Email"
        value=""
        onChange={vi.fn()}
        hint="We send the invoice here."
        optionalNote="used to sign in"
      />,
    );
    expect(screen.getByText('We send the invoice here.')).toBeInTheDocument();
    expect(screen.getByText('used to sign in')).toBeInTheDocument();

    rerender(<EmailField label="Email" value="" onChange={vi.fn()} error="Enter an email address" />);
    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent('Enter an email address');
    expect(field()).toHaveAttribute('aria-invalid', 'true');
  });

  it('accepts an action beside the label — this is where "Verified" goes', () => {
    // Verification state is the caller's, not the control's: only the server knows it.
    render(
      <EmailField label="Email" value="ada@example.com" onChange={vi.fn()} action={<span>Verified</span>} />,
    );
    expect(screen.getByText('Verified')).toBeInTheDocument();
  });
});

describe('EmailField — typing and tidying', () => {
  it('reports the value, not the event', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<EmailField label="Email" value="" onChange={onChange} />);

    await user.type(field(), 'a');

    expect(onChange).toHaveBeenCalledWith('a');
  });

  it('does not tidy while typing — that would fight the caret', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<EmailField label="Email" value="Ada@EXAMPLE.CO" onChange={onChange} />);

    await user.type(field(), 'M');

    // The domain is still shouting; it is not this control's business until the field is left.
    expect(onChange).toHaveBeenCalledWith('Ada@EXAMPLE.COM');
  });

  it('tidies on blur', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<EmailField label="Email" value=" Ada Lovelace <Ada@EXAMPLE.com> " onChange={onChange} />);

    await user.click(field());
    await user.tab();

    expect(onChange).toHaveBeenCalledWith('Ada@example.com');
  });

  it('stays quiet on blur when there is nothing to tidy', async () => {
    // A no-op `onChange` on every blur would mark a pristine form dirty and re-run validation.
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<EmailField label="Email" value="ada@example.com" onChange={onChange} />);

    await user.click(field());
    await user.tab();

    expect(onChange).not.toHaveBeenCalled();
  });

  it('leaves the value exactly as typed when normalization is turned off', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <EmailField label="Email" value=" Ada@EXAMPLE.com " onChange={onChange} normalizeOnBlur={false} />,
    );

    await user.click(field());
    await user.tab();

    expect(onChange).not.toHaveBeenCalled();
  });

  it("still calls the caller's own onBlur", async () => {
    const onBlur = vi.fn();
    const user = userEvent.setup();
    render(<EmailField label="Email" value=" ada@example.com " onChange={vi.fn()} onBlur={onBlur} />);

    await user.click(field());
    await user.tab();

    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it('hands that onBlur the tidied address, not the raw one', async () => {
    /*
     * Read inside the handler, because that is the only moment a caller has: validating on blur
     * means reading `event.target.value` there. Handing over `Ada Lovelace <ada@example.com>` —
     * an address this control is in the middle of fixing — failed `isEmailLike` and put a
     * "not a valid email" error under a field that then showed a perfectly valid one.
     */
    const seen: string[] = [];
    const user = userEvent.setup();
    render(
      <EmailField
        label="Email"
        value="Ada Lovelace <ADA@Example.com>"
        onChange={vi.fn()}
        onBlur={(event) => seen.push(event.target.value)}
      />,
    );

    await user.click(field());
    await user.tab();

    // The local part keeps its case, as everywhere else — only the wrapper and the domain change.
    expect(seen).toEqual(['ADA@example.com']);
  });

  it('is disabled when told to be', () => {
    render(<EmailField label="Email" value="" onChange={vi.fn()} disabled />);
    expect(field()).toBeDisabled();
  });
});
