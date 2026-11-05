import type { ReactNode } from 'react';
import { isSafeHref } from '../lib/url';

export type AppFooterLink = { label: string; href: string; icon?: ReactNode };

/**
 * The page's foot: icon links left, copyright right. It sits inside the scrolling content
 * region rather than being pinned, so it marks the end of the page instead of stealing a
 * band of every screen.
 *
 * **Render it as a sibling of `<main>`, not inside it** — `AppShell`'s `footer` slot does
 * exactly that. A `<footer>` descended from `main` maps to `generic` rather than to the
 * `contentinfo` landmark, so nesting it silently removes the landmark.
 */
export function AppFooter({
  links,
  copyright,
}: {
  links: AppFooterLink[];
  copyright: string;
}) {
  return (
    <footer className="pms-app-footer">
      <ul className="pms-app-footer__links">
        {links.map((link) => {
          const Link = isSafeHref(link.href) ? 'a' : 'span';
          return (
            <li key={link.href}>
              <Link className="pms-app-footer__link" href={Link === 'a' ? link.href : undefined}>
                {link.icon ? (
                  <span className="pms-app-footer__icon" aria-hidden="true">
                    {link.icon}
                  </span>
                ) : null}
                <span>{link.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="pms-app-footer__copy">{copyright}</p>
    </footer>
  );
}
