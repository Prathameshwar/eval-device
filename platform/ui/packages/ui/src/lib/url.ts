/**
 * URL safety for hrefs that came from a payload.
 *
 * Any `href` the UI renders from server data is attacker-controlled in the cases that matter: a
 * supplier's website, a customer's portal link, a document URL. Left unguarded, `javascript:alert(1)`
 * in a response field executes on click, in the reader's session, with their authority
 * — and it is one field on one screen away at all times, which is why the check lives
 * here rather than in each component that renders a link.
 */

/**
 * Whitespace and control characters, which a browser strips before it resolves a scheme.
 *
 * `\s` covers space, tab, the line breaks and NBSP; `\p{Cc}` covers every C0 and C1 control
 * character, NUL included. Both, because either alone leaves a gap.
 */
const IGNORED_IN_SCHEME = /[\s\p{Cc}]/gu;

/**
 * Whether an href may be rendered as a link.
 *
 * An **allowlist**, not a `javascript:` denylist: `data:`, `blob:`, `vbscript:` and `file:` are each
 * their own problem, and the next scheme a browser ships is in no denylist written today. What a
 * business application links to is a page, a route, an anchor, an address or a number.
 *
 * A single leading slash is a route; **two are a host**, so `//evil.test` is an off-site navigation
 * disguised as a path — allowed by every naive "starts with a slash" check ever written. An absolute
 * URL has to declare `http:` or `https:`. A slash followed by a backslash is also a host:
 * browsers normalize backslashes in HTTP paths before resolving the destination.
 *
 * The ignored characters are removed **before** the test, because the browser removes them when
 * resolving the scheme: a `javascript:` URL with a newline inside the scheme is still a
 * `javascript:` URL by the time it matters, while a naive `startsWith` check sees a relative path.
 *
 * A rejected href should degrade to plain text rather than to an anchor with no destination — an
 * empty `<a>` is still a tab stop, still announced as a link, and still leads nowhere.
 */
export function isSafeHref(href: string): boolean {
  return /^(https?:|\/(?![\/\\])|#|mailto:|tel:)/i.test(href.replace(IGNORED_IN_SCHEME, ''));
}
