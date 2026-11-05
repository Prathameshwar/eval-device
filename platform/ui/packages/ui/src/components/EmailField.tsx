'use client';

import { type FocusEvent, type InputHTMLAttributes, type ReactNode } from 'react';
import { TextField } from './TextField';
import { MailIcon } from './icons';

/**
 * `EmailField` — an email address.
 *
 * A `TextField` with the six attributes an email input needs and one behaviour it needs: the
 * tidy-up on blur. Worth a component rather than a convention because those attributes are wrong
 * on at least one screen every time they are retyped — `autoCapitalize` is the one everyone
 * forgets, and on iOS it capitalises the first letter of an address that is then rejected by a
 * case-sensitive local part.
 *
 * **It reports a value, not an event** — the same shape as `Select` and `SearchSelect`. A control
 * that rewrites what was typed has to own the value, and one that owns the value has no business
 * handing back an event whose `target.value` is already stale.
 *
 * It does **not** decide whether the address is valid. `isEmailLike` is exported so the caller's
 * form validation and this field agree on the rule, and the real answer comes from the server and
 * from the verification mail actually arriving.
 */

/** Whitespace, zero-width and bidi marks — none of which belong in an address. */
const NOISE = /[\s\u200B-\u200F\u2060\u202A-\u202E\u2066-\u2069\u061C]/g;

/**
 * Tidies a pasted address without changing what it addresses.
 *
 * Every rule here is something a paste actually contains: `Ada Lovelace <ada@example.com>` from a
 * mail client, a `mailto:` from a copied link, a trailing space from a spreadsheet cell.
 *
 * The domain is lowercased and **the local part is not**: domains are case-insensitive (RFC 1035)
 * while local parts are formally case-*sensitive*. Lowercasing the whole address is what most
 * providers do in practice, and doing it here would silently rewrite an address for the minority
 * of servers that honour the spec.
 */
export function normalizeEmail(raw: string): string {
  const bracketed = raw.match(/<([^<>]*)>/);
  let value = (bracketed?.[1] ?? raw).replace(NOISE, '');
  if (/^mailto:/i.test(value)) value = value.slice('mailto:'.length);

  const at = value.lastIndexOf('@');
  if (at === -1) return value;
  return `${value.slice(0, at)}@${value.slice(at + 1).toLowerCase()}`;
}

/**
 * A typo guard, deliberately permissive: one `@`, something on the left, and a dotted domain.
 *
 * Not RFC 5322 — the full grammar admits quoted local parts and comments, and every regex that
 * claims to implement it rejects deliverable addresses instead. The failure mode of being strict
 * here is a customer who cannot be invited; the failure mode of being loose is a verification
 * mail that bounces, which the system already handles.
 *
 * 320 is `VARCHAR(320)` in identity-schema — 64 for the
 * local part plus `@` plus 255 for the domain.
 */
export function isEmailLike(value: string): boolean {
  return value.length <= 320 && /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/.test(value);
}

type EmailFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'className' | 'type' | 'value' | 'onChange'
> & {
  label: string;
  value: string;
  /** The address, already normalized when the change came from a blur. */
  onChange: (value: string) => void;
  optionalNote?: string;
  /** Beside the label — a "Verified" `Badge`, say, or a link to change it. */
  action?: ReactNode;
  hint?: ReactNode;
  error?: string;
  /** Leave what was typed exactly as typed. Off is almost always wrong; it exists for a diff view. */
  normalizeOnBlur?: boolean;
};

export function EmailField({
  label,
  value,
  onChange,
  optionalNote,
  action,
  hint,
  error,
  normalizeOnBlur = true,
  onBlur,
  ...input
}: EmailFieldProps) {
  return (
    <TextField
      label={label}
      optionalNote={optionalNote}
      action={action}
      hint={hint}
      error={error}
      leading={<MailIcon size={18} />}
      type="email"
      /* `inputMode` gets the `@` onto the phone keyboard's first layer; `autoCapitalize` and
       * `autoCorrect` stop the platform "helping" with a string that is not prose. */
      inputMode="email"
      autoComplete="email"
      autoCapitalize="none"
      autoCorrect="off"
      spellCheck={false}
      /* The column is `VARCHAR(320)`; a longer address cannot be stored, so it is not accepted. */
      maxLength={320}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={(event: FocusEvent<HTMLInputElement>) => {
        /* On blur, not on every keystroke: normalizing mid-typing fights the caret, and someone
         * typing `A` before `da@` would watch it change under them. */
        if (normalizeOnBlur) {
          const tidy = normalizeEmail(event.target.value);
          if (tidy !== event.target.value) {
            /*
             * Written back onto the input before the caller's handler runs, because reading
             * `event.target.value` on blur is how validation-on-blur is written. Handing over the
             * raw `Ada Lovelace <ada@example.com>` failed `isEmailLike` and put "not a valid
             * email" under a field that the very next render showed as valid. React reconciles
             * to the same string once `onChange` lands, so this is the value either way.
             */
            event.target.value = tidy;
            onChange(tidy);
          }
        }
        onBlur?.(event);
      }}
      {...input}
    />
  );
}
