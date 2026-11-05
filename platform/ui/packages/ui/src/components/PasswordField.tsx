'use client';

import { useState, type InputHTMLAttributes, type KeyboardEvent, type ReactNode } from 'react';
import { TextField } from './TextField';
import { LockIcon } from './icons';

/**
 * `PasswordField` — a password, with a strength meter that means something.
 *
 * Three things it deliberately does not do:
 *
 * - **It never blocks paste.** Blocking paste is how a password manager gets defeated, which trades
 *   a theoretical shoulder-surfing risk for the certainty of weaker, reused, hand-typed passwords.
 * - **It never sends the password anywhere to be scored.** The assessment is local and cheap; a
 *   "check this against breach lists" call belongs on the server, over the hash prefix, not here.
 * - **It is not the policy.** The meter advises; the server decides. Scoring in the browser is
 *   advice a hostile client can simply not run.
 */

/** 0–4. Named so the meter, the advice line and any submit guard cannot disagree. */
export type PasswordAssessment = {
  score: number;
  /** The one-or-two-word verdict shown under the meter. */
  label: string;
  /** What would improve it — or the reason it was capped. */
  advice: string;
};

/** The verdict for a score. A `switch`, not an array, so no index can be out of range. */
function verdictFor(score: number): string {
  if (score <= 0) return 'Too short';
  if (score === 1) return 'Weak';
  if (score === 2) return 'Fair';
  if (score === 3) return 'Good';
  return 'Strong';
}

/** A password that is nothing but one character, or one straight run of them. */
function isTrivialSequence(value: string): boolean {
  if (value.length < 3) return false;
  const codes = [...value].map((character) => character.codePointAt(0) ?? 0);
  const step = (codes[1] ?? 0) - (codes[0] ?? 0);
  /* Only 0 (`aaaaaaaa`), +1 (`abcdefgh`, `12345678`) and −1 (`87654321`) count. The comparison is
   * case-sensitive on purpose: `Abcdefgh` is a capital followed by a run, not a run, and treating
   * it as one would punish the shift key. */
  if (step !== 0 && step !== 1 && step !== -1) return false;
  return codes.every((code, index) => index === 0 || code - (codes[index - 1] ?? 0) === step);
}

/**
 * Scores a password out of 4, and says why.
 *
 * The rules, in the order they apply:
 *
 * | Rule | Effect |
 * |---|---|
 * | Under 8 characters | 0 — nothing else is considered |
 * | Contains something from `avoid` (4+ characters) | 0, "Too guessable" |
 * | One character or one straight run | capped at 1 |
 * | Lower **and** upper case · a digit · a symbol · 16+ characters | +1 each, capped at 4 |
 *
 * The length bonus is what stops a long passphrase — the strongest thing most people will type —
 * from scoring below a short `P@ss1` that ticks every character-class box.
 *
 * `avoid` catches the reuse the caller can actually see: the email address and name being typed
 * into the same form. A four-character floor keeps it from matching an initial or a `.com`.
 */
export function assessPassword(value: string, avoid: readonly string[] = []): PasswordAssessment {
  const missing: string[] = [];
  if (value.length < 8) missing.push('8+ characters');
  if (!/\d/.test(value)) missing.push('a number');
  if (!/[^A-Za-z0-9]/.test(value)) missing.push('a symbol');
  const advice = missing.length > 0 ? `Add ${missing.join(', ')}` : 'Looks strong';

  if (value.length < 8) return { score: 0, label: verdictFor(0), advice };

  const lower = value.toLowerCase();
  const guessable = avoid.some((token) => {
    const needle = token.trim().toLowerCase();
    return needle.length >= 4 && lower.includes(needle);
  });
  if (guessable) {
    return {
      score: 0,
      label: 'Too guessable',
      advice: 'Avoid your name, email address or anything else on this form',
    };
  }

  let score = 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score++;
  if (/\d/.test(value)) score++;
  if (/[^A-Za-z0-9]/.test(value)) score++;
  if (value.length >= 16) score++;
  score = Math.min(4, score);

  if (isTrivialSequence(value)) {
    return {
      score: Math.min(1, score),
      label: verdictFor(1),
      advice: 'A single repeated character or a run like this is guessed first',
    };
  }

  return { score, label: verdictFor(score), advice };
}

/** The score alone, for a submit guard that only needs the number. */
export function scorePassword(value: string): number {
  return assessPassword(value).score;
}

type PasswordFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  label: string;
  action?: ReactNode;
  hint?: ReactNode;
  error?: string;
  /**
   * Which password this is. Drives `autocomplete` — `new-password` is what tells a password
   * manager to *offer to generate* one instead of filling the old one, so getting this wrong is
   * the difference between a suggested strong password and a silent autofill of the wrong value.
   * It also defaults the meter on, since strength advice is only useful while choosing.
   */
  purpose?: 'current' | 'new';
  /** Override the meter: on for `current` (a change-password screen), off for `new`. */
  showStrength?: boolean;
  /** Values that must not appear inside the password — typically the email and name on this form. */
  avoid?: readonly string[];
  value?: string;
};

export function PasswordField({
  label,
  action,
  hint,
  error,
  purpose = 'current',
  showStrength = purpose === 'new',
  avoid,
  value = '',
  id,
  autoComplete = purpose === 'new' ? 'new-password' : 'current-password',
  onFocus,
  onBlur,
  onKeyDown,
  onKeyUp,
  ...input
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [focused, setFocused] = useState(false);
  const { score, label: verdict, advice } = assessPassword(value, avoid);

  /* Caps Lock is the classic "correct password, rejected" cause, and the one thing a masked field
   * hides that the user needs to know. Read from the event rather than tracked as a key press:
   * the key may have been pressed before this field ever had focus. */
  function readCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    if (typeof event.getModifierState === 'function') {
      setCapsLock(event.getModifierState('CapsLock'));
    }
  }

  return (
    <>
      <TextField
        label={label}
        action={action}
        hint={hint}
        error={error}
        leading={<LockIcon size={18} />}
        type={visible ? 'text' : 'password'}
        id={id}
        autoComplete={autoComplete}
        /* A password is not prose: autocorrect and capitalisation would silently alter it, and a
         * spellcheck sends what is typed to the platform's dictionary service. */
        spellCheck={false}
        autoCapitalize="none"
        autoCorrect="off"
        value={value}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        onKeyDown={(event) => {
          readCapsLock(event);
          onKeyDown?.(event);
        }}
        onKeyUp={(event) => {
          readCapsLock(event);
          onKeyUp?.(event);
        }}
        trailing={
          <button
            type="button"
            className="pms-input__toggle"
            /* Named, not just labelled by its own word: a create-account form has two of these,
             * and "Show / Show" tells a screen-reader user nothing about which. The visible word
             * stays inside the name, so speech control still works (WCAG 2.5.3). */
            aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
            aria-pressed={visible}
            onClick={() => setVisible((v) => !v)}
          >
            {visible ? 'Hide' : 'Show'}
          </button>
        }
        {...input}
      />
      {/* Only while focused, and only while masked — with the characters on screen, Caps Lock is
        * something the user can already see. */}
      {capsLock && focused && !visible ? (
        <p className="pms-caps" role="status">
          Caps Lock is on
        </p>
      ) : null}
      {showStrength && value.length > 0 ? (
        <div className="pms-strength" data-score={score}>
          {/* The bars restate the words beside them; announcing four empty spans adds nothing. */}
          <div className="pms-strength__track" aria-hidden="true">
            <span className="pms-strength__seg" />
            <span className="pms-strength__seg" />
            <span className="pms-strength__seg" />
            <span className="pms-strength__seg" />
          </div>
          {/* One region, on the line that carries the meaning — not on the whole block, which
            * would re-read the meter's markup on every keystroke. */}
          <div className="pms-strength__label" role="status">
            <span>{verdict}</span>
            <span>{advice}</span>
          </div>
        </div>
      ) : null}
    </>
  );
}
