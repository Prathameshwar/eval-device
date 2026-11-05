/**
 * `PhoneField`.
 *
 * The control's whole job is keeping two values honest: a dial code and a national number that
 * together must still be a phone number. So the tests are mostly about the seams — what a paste
 * does, what changing the country does to digits already typed, and what the picker shows when the
 * stored code is not one it offers.
 *
 * Most behaviour goes through `Harness`, which holds the value in state the way a real form does.
 * A control that only works when its `onChange` is a spy is a control that only works in tests:
 * `+1242` must survive a re-render as `+1242`, not settle back to the first option in the list.
 */
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  PhoneField,
  isPhoneLike,
  nationalMaxLength,
  splitInternational,
  toE164,
  type PhoneDialCode,
  type PhoneValue,
} from '../src/components/PhoneField';

/**
 * `+1` and `+1242` are both here on purpose: they are the pair that catches a prefix match done
 * shortest-first. `AE` carries no label, which is how a narrow layout passes its codes.
 */
const CODES: readonly PhoneDialCode[] = [
  { country: 'IN', dial: '+91', label: 'India' },
  { country: 'US', dial: '+1', label: 'United States' },
  { country: 'BS', dial: '+1242', label: 'Bahamas' },
  { country: 'AE', dial: '+971' },
];

function number(name = 'Mobile number'): HTMLInputElement {
  return screen.getByLabelText(name) as HTMLInputElement;
}

function code(): HTMLSelectElement {
  return screen.getByLabelText('Country dial code') as HTMLSelectElement;
}

function Harness({
  initial = { countryCode: '+91', number: '' },
  onValue,
  ...rest
}: {
  initial?: PhoneValue;
  onValue?: (value: PhoneValue) => void;
} & Partial<React.ComponentProps<typeof PhoneField>>) {
  const [value, setValue] = useState<PhoneValue>(initial);
  return (
    <PhoneField
      label="Mobile number"
      dialCodes={CODES}
      {...rest}
      value={value}
      onChange={(next) => {
        setValue(next);
        onValue?.(next);
      }}
    />
  );
}

describe('nationalMaxLength', () => {
  it.each([
    ['+91', 13],
    ['+1', 14],
    ['+1242', 11],
    // No code chosen yet: the whole E.164 budget, so nothing typed is refused before the country
    // is known and the real cap can be applied.
    ['', 15],
  ])('leaves %j room for %i digits', (dial, expected) => {
    expect(nationalMaxLength(dial)).toBe(expected);
  });
});

describe('toE164', () => {
  it('joins the two halves', () => {
    expect(toE164({ countryCode: '+91', number: '9876543210' })).toBe('+919876543210');
  });

  it('ignores whatever separators the halves carry', () => {
    expect(toE164({ countryCode: '+91 ', number: '98765-43210' })).toBe('+919876543210');
  });

  it.each([
    [{ countryCode: '+91', number: '' }, 'no number'],
    [{ countryCode: '', number: '9876543210' }, 'no country code'],
    [{ countryCode: '', number: '' }, 'nothing at all'],
  ])('returns empty for a half-filled value (%#: %s)', (value) => {
    // A partial value must not become `+91` — a caller that forgot to check would otherwise send
    // a message to a country code.
    expect(toE164(value)).toBe('');
  });
});

describe('isPhoneLike', () => {
  it.each([
    [{ countryCode: '+91', number: '9876543210' }, 'an Indian mobile'],
    [{ countryCode: '+683', number: '1234' }, 'the shortest real number there is'],
    [{ countryCode: '+1', number: '55501234567890' }, 'exactly 15 digits'],
  ])('accepts %#: %s', (value) => {
    expect(isPhoneLike(value)).toBe(true);
  });

  it.each([
    [{ countryCode: '+91', number: '' }, 'no number'],
    [{ countryCode: '', number: '9876543210' }, 'no code'],
    [{ countryCode: '+683', number: '123' }, 'six digits in total'],
    [{ countryCode: '+1', number: '555012345678901' }, 'sixteen digits in total'],
  ])('rejects %#: %s', (value) => {
    expect(isPhoneLike(value)).toBe(false);
  });
});

describe('splitInternational', () => {
  it('splits a pasted number and drops the separators', () => {
    expect(splitInternational('+91 98765 43210', CODES)).toEqual({
      countryCode: '+91',
      number: '9876543210',
    });
  });

  it('takes the longest matching dial code', () => {
    // `+1` also matches. Taking it would leave `242` glued to the front of the national number
    // and file a Bahamian number under the United States.
    expect(splitInternational('+1242 555 1234', CODES)).toEqual({
      countryCode: '+1242',
      number: '5551234',
    });
  });

  it('understands the 00 international prefix', () => {
    expect(splitInternational('00 91 98765 43210', CODES)).toEqual({
      countryCode: '+91',
      number: '9876543210',
    });
  });

  it('honours 00 only for something long enough to be a whole number', () => {
    // `001` is also what a national number beginning `001…` looks like three keystrokes in, and
    // there is nothing in a change event that says which of the two happened.
    expect(splitInternational('001', CODES)).toBeNull();
    expect(splitInternational('001242555', CODES)).toEqual({
      countryCode: '+1242',
      number: '555',
    });
  });

  it('caps the national part at what E.164 leaves', () => {
    const split = splitInternational('+91 123456789012345678', CODES);
    expect(split?.number).toBe('1234567890123');
  });

  it.each([
    ['9876543210', 'no international prefix — it could be a national number'],
    ['+99 12345', 'a dial code the caller does not offer'],
    ['+', 'nothing but a plus'],
    ['', 'nothing'],
  ])('returns null for %j (%s)', (raw) => {
    // Null, not a guess: mangling a paste into the wrong country is worse than leaving it alone.
    expect(splitInternational(raw, CODES)).toBeNull();
  });

  it('ignores a dial code with no digits', () => {
    expect(splitInternational('+91 98765', [{ country: '', dial: '' }, ...CODES])).toEqual({
      countryCode: '+91',
      number: '98765',
    });
  });
});

describe('PhoneField — structure', () => {
  it('gives the visible label to the number, and the picker a name of its own', () => {
    render(<PhoneField label="Mobile number" value={{ countryCode: '+91', number: '' }} dialCodes={CODES} onChange={vi.fn()} />);

    // Two controls sharing one accessible name is worse than no grouping at all, so the label
    // belongs to the field's primary control and the picker names itself.
    expect(number()).toHaveAttribute('type', 'tel');
    expect(code().tagName).toBe('SELECT');
  });

  it('carries the attributes a phone input needs', () => {
    render(<Harness />);
    const input = number();

    expect(input).toHaveAttribute('inputmode', 'tel');
    expect(input).toHaveAttribute('autocomplete', 'tel-national');
  });

  it('does not cap the field with maxlength', () => {
    // The browser applies `maxlength` to a paste before any handler runs, so a pasted
    // `+91 9876543210` would arrive with its last digit already gone.
    render(<Harness />);
    expect(number()).not.toHaveAttribute('maxlength');
  });

  it('shows each code with its country, falling back to the ISO code', () => {
    render(<Harness />);
    const options = screen.getAllByRole('option').map((option) => option.textContent);

    expect(options).toEqual(['+91 India', '+1 United States', '+1242 Bahamas', '+971 AE']);
  });

  it('hides the caret from the accessibility tree', () => {
    const { container } = render(<Harness />);
    expect(container.querySelector('.pms-select__caret')).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders a hint, and swaps it for the error', () => {
    const { rerender } = render(<Harness hint="We send the OTP here." />);
    expect(screen.getByText('We send the OTP here.')).toBeInTheDocument();

    rerender(<Harness hint="We send the OTP here." error="Enter a mobile number" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a mobile number');
    // Only one paragraph renders, so only one id is referenced.
    expect(screen.queryByText('We send the OTP here.')).not.toBeInTheDocument();
    expect(number().getAttribute('aria-describedby')).toBe(
      screen.getByRole('alert').getAttribute('id'),
    );
    // Both halves of the field are invalid together — the value is one thing.
    expect(number()).toHaveAttribute('aria-invalid', 'true');
    expect(code()).toHaveAttribute('aria-invalid', 'true');
  });

  it('marks both halves disabled together', () => {
    render(<Harness disabled />);
    expect(number()).toBeDisabled();
    expect(code()).toBeDisabled();
  });

  it('names both halves for a native form post', () => {
    render(<Harness name="phone" codeName="phone_country_code" />);
    // The two columns the schema actually has.
    expect(number()).toHaveAttribute('name', 'phone');
    expect(code()).toHaveAttribute('name', 'phone_country_code');
  });

  it('shows the optional note, or an action, beside the label', () => {
    const { rerender } = render(<Harness optionalNote="optional" />);
    expect(screen.getByText('optional')).toBeInTheDocument();

    rerender(<Harness optionalNote="optional" action={<span>Verified</span>} />);
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.queryByText('optional')).not.toBeInTheDocument();
  });
});

describe('PhoneField — what the picker shows', () => {
  it('shows a stored code it was never given, rather than a different country', () => {
    // The `Select` trap: rendering only the known options leaves the picker displaying its first
    // option while the value says something else — here, relabelling a UK number as Indian.
    render(<Harness initial={{ countryCode: '+44', number: '2079460958' }} />);

    expect(code().value).toBe('+44');
    expect(screen.getByRole('option', { name: '+44' })).toBeInTheDocument();
  });

  it('shows a placeholder when no code has been chosen, not the first country', () => {
    render(<Harness initial={{ countryCode: '', number: '' }} />);

    expect(code().value).toBe('');
    expect(screen.getByRole('option', { name: 'Code' })).toBeInTheDocument();
  });

  it('drops the placeholder once a code is chosen', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ countryCode: '', number: '' }} />);

    await user.selectOptions(code(), '+91');

    expect(code().value).toBe('+91');
    expect(screen.queryByRole('option', { name: 'Code' })).not.toBeInTheDocument();
  });
});

describe('PhoneField — typing', () => {
  it('keeps digits and drops everything else', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), '98765-43210');

    // Stored bare, because `phone` is bare digits; the separators are a display choice this
    // control does not have the country data to make.
    expect(number().value).toBe('9876543210');
  });

  it('refuses letters outright', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), 'call me');

    expect(number().value).toBe('');
  });

  it('stops at the digits E.164 leaves for the country', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), '12345678901234567890');

    // 15 total, less the two the `+91` takes.
    expect(number().value).toBe('1234567890123');
  });

  it('reports the two halves separately, the way the schema stores them', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Harness onValue={onValue} />);

    await user.type(number(), '9');

    expect(onValue).toHaveBeenCalledWith({ countryCode: '+91', number: '9' });
  });
});

/*
 * Typed, not pasted — and they are different code paths, which is exactly how the bug below got
 * in. A paste arrives as one change event carrying the whole string; typing arrives one character
 * at a time, and the very first one is the `+` that says "this is international".
 */
describe('PhoneField — typing an international number', () => {
  it('takes the country from a number typed with its dial code', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Harness onValue={onValue} />);

    await user.type(number(), '+919876543210');

    // The `+` used to be stripped on the keystroke that carried it, so nothing downstream ever
    // saw an international number: the code stayed glued to the front of the national part and
    // `toE164` rendered `+91919876543210`, which `isPhoneLike` accepted as 14 digits.
    expect(onValue).toHaveBeenLastCalledWith({ countryCode: '+91', number: '9876543210' });
    expect(code().value).toBe('+91');
    expect(number().value).toBe('9876543210');
  });

  it('switches the country to the one the typed code names', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), '+971501234567');

    expect(code().value).toBe('+971');
    expect(number().value).toBe('501234567');
  });

  it('keeps the + on screen until the digits name a country', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), '+9');

    // `9` prefixes no code offered here, so nothing has been decided yet and the field shows what
    // was typed. Dropping the `+` here is what made the next keystroke unrecoverable.
    expect(number().value).toBe('+9');
    expect(code().value).toBe('+91');
  });

  it('gives the digits back as national once no dial code can match', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), '+8888');

    // Four digits is the longest code the ITU issues, so holding out for a match beyond that
    // only keeps the number hostage.
    expect(number().value).toBe('8888');
    expect(code().value).toBe('+91');
  });

  it('lets the + be deleted again', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(number(), '+9');
    await user.type(number(), '{backspace}{backspace}');

    expect(number().value).toBe('');
  });

  it('resolves a shared prefix at the first match, which spells the same number either way', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // `+1` matches on the first digit, so a Bahamian number typed by hand lands as `+1` plus
    // `242…` rather than `+1242`. Only the picker's label differs; the number is the same, and a
    // paste — where the whole string arrives at once — still takes the longest match.
    await user.type(number(), '+12425551234');

    expect(toE164({ countryCode: code().value, number: number().value })).toBe('+12425551234');
  });

  it('does not read the third digit of a national number as an international prefix', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // `001` under `+91` is someone typing a number that begins `001…`. Reading `00` as
    // international mid-typing emptied the field and moved them to the United States.
    await user.type(number(), '001');

    expect(code().value).toBe('+91');
    expect(number().value).toBe('001');
  });
});

describe('PhoneField — pasting a whole number', () => {
  it('splits the dial code out of an international paste', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ countryCode: '+1', number: '' }} />);

    await user.click(number());
    await user.paste('+91 98765 43210');

    expect(code().value).toBe('+91');
    expect(number().value).toBe('9876543210');
  });

  it('keeps every digit of a paste that fills the E.164 budget', async () => {
    // The reason there is no `maxlength`: this paste is 14 characters under a 13-digit cap.
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(number());
    await user.paste('+919876543210');

    expect(number().value).toBe('9876543210');
  });

  it('leaves a national paste under the country already chosen', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ countryCode: '+971', number: '' }} />);

    await user.click(number());
    await user.paste('50 123 4567');

    expect(code().value).toBe('+971');
    expect(number().value).toBe('501234567');
  });

  it('does not guess a country from a paste whose code it does not offer', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(number());
    await user.paste('+44 20 7946 0958');

    // The digits are kept under the chosen country; nothing silently becomes British. The result
    // is not a real number, and it is the caller's `isPhoneLike` and the server that say so — a
    // control that quietly reassigned the country would be wrong in a way nobody could see.
    expect(code().value).toBe('+91');
    expect(number().value).toBe('442079460958');
  });
});

describe('PhoneField — changing the country', () => {
  it('keeps the number when it still fits', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ countryCode: '+91', number: '9876543210' }} />);

    await user.selectOptions(code(), '+1');

    expect(number().value).toBe('9876543210');
  });

  it('trims the number when the new code needs the room', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ countryCode: '+91', number: '1234567890123' }} />);

    await user.selectOptions(code(), '+1242');

    // 15 total, less the four `+1242` takes — otherwise the value stored is not dialable.
    expect(number().value).toBe('12345678901');
  });

  it('reports both halves in one change', async () => {
    const onValue = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={{ countryCode: '+91', number: '9876543210' }} onValue={onValue} />);

    await user.selectOptions(code(), '+971');

    // One call, not a code change followed by a number change: a form that validates on every
    // change must never see a country that does not match the number.
    expect(onValue).toHaveBeenCalledTimes(1);
    expect(onValue).toHaveBeenCalledWith({ countryCode: '+971', number: '9876543210' });
  });
});
