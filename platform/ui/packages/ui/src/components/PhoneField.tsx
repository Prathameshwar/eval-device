'use client';

import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { AlertIcon } from './icons';
import { ChevronDownIcon } from './icons-console';

/**
 * `PhoneField` — a dial code and a national number.
 *
 * **Two values, because the schema stores two.** `phone_country_code VARCHAR(8)` and
 * `phone VARCHAR(20)` are separate columns in identity-schema;
 * a control that reported one `+919876543210` string would force every caller to split it again,
 * and they would each split it differently. `toE164` is exported for the transports that genuinely
 * need one string — SMS and WhatsApp delivery (notification).
 *
 * **The dial codes are a prop, not a table in here.** `country.phone_prefix` is the platform's one
 * source for them; a list baked into the design system would be a second source, and the second
 * source is always the stale one.
 *
 * It does not pretty-print as you type. Digit grouping is per-country data (and per-length within
 * a country), so formatting without that data produces confident nonsense — `+91 987 654 3210` for
 * a number Indians read as `98765 43210`. Storing and showing the digits the user typed is honest;
 * the server, which has the country data, is what validates.
 */

/** One row of the picker. Build these from the `country` reference table, not by hand. */
export type PhoneDialCode = {
  /** ISO-3166 alpha-2, e.g. `IN`. Used as the option's React key. */
  country: string;
  /** `country.phone_prefix`, with its `+`, e.g. `+91`. */
  dial: string;
  /** Shown after the dial code. Defaults to `country`; pass the country name when there is room. */
  label?: string;
};

export type PhoneValue = {
  /** The dial code with its `+` — what goes in `phone_country_code`. */
  countryCode: string;
  /** National digits only, no spaces or separators — what goes in `phone`. */
  number: string;
};

/** E.164's ceiling: 15 digits including the country calling code. */
const E164_MAX = 15;
/**
 * The shortest real international number: `+683` plus four digits (Niue).
 *
 * Used twice — as the floor `isPhoneLike` accepts, and as the length a `00`-prefixed string has to
 * reach before it is read as a whole international number rather than as digits still being typed.
 */
const E164_MIN = 7;
/** The longest calling code the ITU issues (`+1242`, `+1809`). Past this, nothing can match. */
const DIAL_DIGITS_MAX = 4;

function digitsOf(value: string): string {
  return value.replace(/\D/g, '');
}

/** How many national digits still fit once the dial code has taken its share. */
export function nationalMaxLength(countryCode: string): number {
  return Math.max(1, E164_MAX - digitsOf(countryCode).length);
}

/**
 * The one string form: `+919876543210`, or `''` if either half is missing.
 *
 * Empty rather than a partial number on purpose — `+91` alone is not a phone number, and a caller
 * that forgets to check would otherwise send a message to a country code.
 */
export function toE164(value: PhoneValue): string {
  const dial = digitsOf(value.countryCode);
  const national = digitsOf(value.number);
  if (!dial || !national) return '';
  return `+${dial}${national}`;
}

/**
 * A shape check, not a reachability check: both halves present, 7–15 digits in total.
 *
 * 7 is the shortest real international number (+683 plus four digits, Niue); 15 is E.164's limit.
 * Anything tighter rejects a live number somewhere, and the only true test of a mobile number is
 * an OTP arriving on it.
 */
export function isPhoneLike(value: PhoneValue): boolean {
  const dial = digitsOf(value.countryCode);
  const national = digitsOf(value.number);
  if (!dial || !national) return false;
  const total = dial.length + national.length;
  return total >= E164_MIN && total <= E164_MAX;
}

/**
 * Splits a pasted international number into its two halves, longest dial code first.
 *
 * Longest-first matters: `+1` and `+1242` both exist, and taking `+1` for a Bahamian number would
 * leave `242` glued to the front of the national part. Returns `null` when nothing matches, so a
 * paste is never silently mangled into the wrong country.
 */
export function splitInternational(
  raw: string,
  dialCodes: readonly PhoneDialCode[],
): PhoneValue | null {
  let digits = digitsOf(raw);
  if (!raw.trimStart().startsWith('+')) {
    /*
     * `00` is the international prefix everywhere the ITU didn't hand out `011`; a paste from a
     * European phone book starts with it. Honoured only for a string already long enough to be a
     * whole number, because `001` is equally what a national number beginning `001…` looks like
     * three keystrokes in — and reading that as `+1` moved the typist to another country and
     * emptied the field under them. A leading `+` needs no such test: it is unambiguous intent.
     */
    if (!digits.startsWith('00') || digits.length - 2 < E164_MIN) return null;
    digits = digits.slice(2);
  }

  const match = dialCodes
    .map((code) => digitsOf(code.dial))
    .filter((dial) => dial.length > 0 && digits.startsWith(dial))
    .sort((a, b) => b.length - a.length)[0];
  if (!match) return null;

  return {
    countryCode: `+${match}`,
    number: digits.slice(match.length).slice(0, nationalMaxLength(match)),
  };
}

type PhoneFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'className' | 'type' | 'value' | 'onChange' | 'maxLength'
> & {
  label: string;
  value: PhoneValue;
  onChange: (value: PhoneValue) => void;
  /** From the `country` table: `{ country: 'IN', dial: '+91', label: 'India' }`. */
  dialCodes: readonly PhoneDialCode[];
  optionalNote?: string;
  action?: ReactNode;
  hint?: ReactNode;
  error?: string;
  /** `name` for the dial-code select, if the form is posted natively. */
  codeName?: string;
};

export function PhoneField({
  label,
  value,
  onChange,
  dialCodes,
  optionalNote,
  action,
  hint,
  error,
  codeName,
  id,
  disabled,
  autoComplete = 'tel-national',
  ...input
}: PhoneFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  /* Only the paragraph that actually renders is referenced — a describedby pointing at an absent
   * id is read as nothing at all by some screen readers, and as a bug by all of them. */
  const describedBy = error ? errorId : hint ? hintId : undefined;

  const maxLength = nationalMaxLength(value.countryCode);

  /*
   * An international number being *typed*, held while it is still too short to name a country.
   *
   * `value.number` is digits only, so the `+` that says "this is international" has nowhere to
   * live in it — and stripping it on the keystroke that carried it meant `splitInternational`
   * could only ever fire for a paste. Typed input fell through to the national branch, which left
   * the dial code glued to the front of the national number: `+91` selected and `+919876543210`
   * typed produced `+91919876543210` from `toE164`, and `isPhoneLike` accepted it as 14 digits.
   *
   * `null` whenever the field is showing its stored value, which is every moment except between
   * the `+` and the digit that identifies the country.
   */
  const [pendingCode, setPendingCode] = useState<string | null>(null);

  /*
   * A stored code the picker doesn't offer still has to show itself. Rendering only the known
   * codes would leave the select displaying its *first* option while the value said something
   * else — the same silent lie `Select` fixes, and here it would relabel a supplier's number as
   * belonging to another country. Same treatment for an empty code, which is not "the first
   * country in the list".
   */
  const known = dialCodes.some((code) => code.dial === value.countryCode);
  const extra: PhoneDialCode | null = known
    ? null
    : { country: '', dial: value.countryCode, label: value.countryCode ? undefined : 'Code' };

  function commit(next: Partial<PhoneValue>) {
    onChange({ ...value, ...next });
  }

  return (
    <div className="pms-field pms-phone">
      <div className="pms-field__row">
        <label className="pms-label" htmlFor={inputId}>
          {label}
        </label>
        {action ?? (optionalNote ? <span className="pms-optional">{optionalNote}</span> : null)}
      </div>
      <div className="pms-input-wrap pms-phone__wrap">
        {/* `pms-select__*` on purpose: the dial code *is* a select, and giving it a second box
          * model would let the two drift a pixel apart on the one screen showing both. */}
        <span className="pms-select__wrap pms-phone__code-wrap">
          <select
            /* Self-named: the visible label belongs to the number input, and two controls sharing
             * one accessible name is worse than no grouping at all. */
            aria-label="Country dial code"
            className="pms-input pms-select__control pms-phone__code"
            name={codeName}
            value={value.countryCode}
            disabled={disabled}
            aria-invalid={error ? true : undefined}
            onChange={(event) => {
              const countryCode = event.target.value;
              /* Choosing a country answers the question a half-typed `+…` was asking. */
              setPendingCode(null);
              /* Switching country can shorten the room left for national digits — an Indian
               * number pasted under `+1` must not stay 12 digits long once the code is 4. */
              commit({
                countryCode,
                number: value.number.slice(0, nationalMaxLength(countryCode)),
              });
            }}
          >
            {extra ? <option value={extra.dial}>{extra.label ?? extra.dial}</option> : null}
            {dialCodes.map((code) => (
              <option key={code.country || code.dial} value={code.dial}>
                {`${code.dial} ${code.label ?? code.country}`}
              </option>
            ))}
          </select>
          <span className="pms-select__caret" aria-hidden="true">
            <ChevronDownIcon size={14} />
          </span>
        </span>
        <input
          id={inputId}
          className="pms-input pms-phone__number"
          type="tel"
          inputMode="tel"
          autoComplete={autoComplete}
          /*
           * No `maxLength` attribute, deliberately — the browser applies it to a *paste* before
           * any handler runs, so pasting `+91 9876543210` under a 13-digit cap arrives already
           * truncated and the number loses its last digit in silence. The cap below does the same
           * job after the dial code has been taken off the front, which is the only point at
           * which the right length is known.
           */
          value={pendingCode ?? value.number}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            const raw = event.target.value;
            /* A `+91 98765 43210` — pasted whole, or typed to the digit that identifies it —
             * carries its own country; honour it rather than dropping the code and leaving a
             * 12-digit "national" number. */
            const international = splitInternational(raw, dialCodes);
            if (international) {
              setPendingCode(null);
              onChange(international);
              return;
            }
            const digits = digitsOf(raw);
            /* Mid-air: a `+` is on screen but too few digits have followed it to match a code, so
             * hold what was typed rather than discarding the one character that carries the
             * intent. Past the longest code the ITU issues nothing can match, and holding out
             * further would keep the number hostage — so the digits become national. */
            if (raw.includes('+') && digits.length < DIAL_DIGITS_MAX) {
              setPendingCode(`+${digits}`);
              /* Never both: whatever is on screen is the value, or the field is lying about what
               * a submit would carry. */
              if (value.number !== '') commit({ number: '' });
              return;
            }
            setPendingCode(null);
            commit({ number: digits.slice(0, maxLength) });
          }}
          {...input}
        />
      </div>
      {error ? (
        <p className="pms-error" id={errorId} role="alert">
          <AlertIcon size={14} />
          {error}
        </p>
      ) : hint ? (
        <p className="pms-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
