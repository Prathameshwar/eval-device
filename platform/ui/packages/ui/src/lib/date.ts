/** The current year, resolved at render time so a footer never goes stale. */
export function currentYear(): number {
  return new Date().getFullYear();
}
