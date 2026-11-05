/**
 * Initials avatar. `shape="square"` is an organisation, `"round"` is a person — the shape
 * is the only cue that distinguishes the org switcher's tile from the user menu's, so it
 * carries meaning rather than decoration.
 */

export type AvatarShape = 'square' | 'round';
export type AvatarSize = 'sm' | 'md' | 'lg';

/**
 * First + last initial, because that is how a person's name is abbreviated everywhere
 * else; a single-word name gives up its first two letters instead of one lonely glyph.
 */
function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const first = words[0];
  if (first === undefined) return '';

  const last = words.length > 1 ? words[words.length - 1] : undefined;
  const initials = last === undefined ? first.slice(0, 2) : first.charAt(0) + last.charAt(0);
  return initials.toUpperCase();
}

export function Avatar({
  name,
  shape = 'round',
  size = 'md',
  label,
  className = '',
}: {
  name: string;
  shape?: AvatarShape;
  size?: AvatarSize;
  /**
   * Only pass this when the avatar stands alone. Beside a visible name it is decorative,
   * and announcing "AC, Acme Corp" reads the same thing twice.
   */
  label?: string;
  className?: string;
}) {
  const classes = [
    'pms-avatar',
    `pms-avatar--${shape}`,
    `pms-avatar--${size}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const initials = initialsFrom(name);

  if (label) {
    return (
      <span className={classes} role="img" aria-label={label}>
        {initials}
      </span>
    );
  }

  return (
    <span className={classes} aria-hidden="true">
      {initials}
    </span>
  );
}
