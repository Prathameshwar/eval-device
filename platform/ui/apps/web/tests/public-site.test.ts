import { expect, it } from 'vitest';
import { publicSite } from '../src/lib/public-site';
import { generateMetadata } from '../src/app/page';

it('uses the owner-approved public identity and functional local policy links', () => {
  expect(publicSite({})).toEqual({ contactEmail: 'contact@aieval.com', contactHref: 'mailto:contact@aieval.com', operatorName: 'AI Evaluator Company', siteUrl: 'https://eval.centralindia.cloudapp.azure.com/', privacyHref: '/privacy', termsHref: '/terms', indexingEnabled: false });
});

it('uses deliberate public contact and operator values', () => {
  const result = publicSite({ PMS_PUBLIC_CONTACT_EMAIL: ' hello+training@example.com ', PMS_PUBLIC_OPERATOR_NAME: ' Example Institution ', PMS_PUBLIC_SITE_URL: 'https://example.com', PMS_PUBLIC_INDEXING_ENABLED: 'true' });
  expect(result.contactHref).toBe('mailto:hello+training@example.com');
  expect(result.operatorName).toBe('Example Institution');
  expect(result.siteUrl).toBe('https://example.com/');
  expect(result.indexingEnabled).toBe(true);
});

it.each(['hello@example.com?subject=other', 'hello@example.com\r\nBcc:other@example.com', 'mailto:hello@example.com', 'not-an-email'])('rejects unsafe contact input: %s', value => {
  expect(() => publicSite({ PMS_PUBLIC_CONTACT_EMAIL: value })).toThrow('public contact email');
});

it.each(['javascript:alert(1)', 'http://example.com', 'https://user:password@example.com', 'https://example.com/?token=private', 'https://example.com/#private'])('rejects unsafe public destinations: %s', value => {
  expect(() => publicSite({ PMS_PUBLIC_TERMS_URL: value })).toThrow('HTTPS URLs');
});

it('requires an origin and an explicit indexing opt-in', () => {
  expect(() => publicSite({ PMS_PUBLIC_SITE_URL: 'https://example.com/private/path' })).toThrow('website origin');
  expect(() => publicSite({ PMS_PUBLIC_INDEXING_ENABLED: 'yes' })).toThrow('true or false');
  expect(publicSite({ PMS_PUBLIC_INDEXING_ENABLED: 'true', PMS_PUBLIC_SITE_URL: '' }).indexingEnabled).toBe(false);
  expect(publicSite({ PMS_PUBLIC_SITE_URL: 'https://example.com' }).indexingEnabled).toBe(false);
});

it('adds no authentication URL to public canonical metadata', () => {
  const metadata = generateMetadata();
  expect(metadata.description).toContain('patient scenarios');
  expect(metadata.robots).toEqual({ index: false, follow: false });
  expect(metadata.alternates).toEqual({ canonical: 'https://eval.centralindia.cloudapp.azure.com/' });
});
