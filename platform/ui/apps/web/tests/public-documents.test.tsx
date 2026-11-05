import { render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
vi.mock('../src/lib/session', () => ({ currentUser: vi.fn().mockResolvedValue(undefined) }));
import PrivacyPage from '../src/app/privacy/page';
import TermsPage from '../src/app/terms/page';
import { LandingPage } from '../src/components/landing/LandingPage';
import { publicSite } from '../src/lib/public-site';

it.each([
  [PrivacyPage, 'Privacy & data use'],
  [TermsPage, 'Terms of use'],
] as const)('renders the public document with homepage navigation', async (Page, title) => {
  render(await Page());
  expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
  const nav = screen.getByRole('navigation', { name: 'Main navigation' });
  expect(within(nav).getByRole('link', { name: 'Meet Alex' })).toHaveAttribute('href', '/#alex');
  expect(screen.getByRole('navigation', { name: 'Legal information' })).toBeInTheDocument();
});

it('uses configured contact and legal destinations on the homepage', () => {
  const site = publicSite({ PMS_PUBLIC_CONTACT_EMAIL: 'hello@example.com', PMS_PUBLIC_OPERATOR_NAME: 'Example Operator', PMS_PUBLIC_PRIVACY_URL: 'https://example.com/privacy', PMS_PUBLIC_TERMS_URL: 'https://example.com/terms' });
  render(<LandingPage signedIn={false} site={site} />);
  const section = screen.getByRole('region', { name: /Explore AI Evaluator/ });
  expect(within(section).getByRole('link', { name: 'Contact Us' })).toHaveAttribute('href', 'mailto:hello@example.com');
  expect(screen.getByRole('link', { name: 'Privacy & data use' })).toHaveAttribute('href', site.privacyHref);
  expect(screen.getByRole('link', { name: 'Terms of use' })).toHaveAttribute('href', site.termsHref);
});
