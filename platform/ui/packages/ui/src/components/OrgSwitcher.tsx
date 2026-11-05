'use client';

import { Avatar } from './Avatar';
import { ChevronUpDownIcon } from './icons-console';

/**
 * The organisation (company) switcher at the head of the rail.
 *
 * A button opening a listbox rather than a native `<select>`: the option rows carry an
 * avatar, a code and a name, which a `<select>` cannot render, and the list is often
 * fetched. The popup itself is the caller's — the rail owns the affordance, not the data.
 */
export function OrgSwitcher({
  name,
  code,
  onOpen,
  open = false,
}: {
  name: string;
  code: string;
  onOpen?: () => void;
  open?: boolean;
}) {
  return (
    <button
      type="button"
      className="pms-org"
      aria-haspopup="listbox"
      aria-expanded={open}
      onClick={onOpen}
    >
      <span className="pms-visually-hidden">Switch organisation</span>
      <Avatar name={name} shape="square" size="md" />
      <span className="pms-org__text">
        <span className="pms-org__code">{code}</span>
        <span className="pms-org__name">{name}</span>
      </span>
      <ChevronUpDownIcon className="pms-org__chevron" />
    </button>
  );
}
