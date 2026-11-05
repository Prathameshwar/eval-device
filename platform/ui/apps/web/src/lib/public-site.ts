/** Only deliberate, non-sensitive public values belong in this configuration. */
export type PublicSite = {
  contactEmail?: string;
  contactHref?: string;
  operatorName?: string;
  siteUrl?: string;
  privacyHref: string;
  termsHref: string;
  indexingEnabled: boolean;
};

/** Public identity supplied by the product owner on 2026-10-08. */
const approvedDefaults = {
  PMS_PUBLIC_CONTACT_EMAIL: 'contact@aieval.com',
  PMS_PUBLIC_OPERATOR_NAME: 'AI Evaluator Company',
  PMS_PUBLIC_SITE_URL: 'https://eval.centralindia.cloudapp.azure.com/',
};

function secureUrl(value: string | undefined): string | undefined {
  if (!value?.trim()) return undefined;
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error();
    return url.toString();
  } catch {
    throw new Error('Public website and policy destinations must be HTTPS URLs without credentials, query strings, or fragments.');
  }
}

export function publicSite(env: Record<string, string | undefined> = process.env): PublicSite {
  const contactEmail = (env.PMS_PUBLIC_CONTACT_EMAIL ?? approvedDefaults.PMS_PUBLIC_CONTACT_EMAIL).trim() || undefined;
  if (contactEmail && (contactEmail.length > 254 || !/^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$/.test(contactEmail))) {
    throw new Error('Configure a valid public contact email address.');
  }
  const operatorName = (env.PMS_PUBLIC_OPERATOR_NAME ?? approvedDefaults.PMS_PUBLIC_OPERATOR_NAME).trim() || undefined;
  if (operatorName && (operatorName.length > 160 || /[\r\n\x00-\x1f]/.test(operatorName))) {
    throw new Error('Configure a single-line public operator name.');
  }
  const siteUrl = secureUrl(env.PMS_PUBLIC_SITE_URL ?? approvedDefaults.PMS_PUBLIC_SITE_URL);
  if (siteUrl && new URL(siteUrl).pathname !== '/') {
    throw new Error('Public site URL must identify the website origin.');
  }
  const indexing = env.PMS_PUBLIC_INDEXING_ENABLED?.trim();
  if (indexing && !['true', 'false'].includes(indexing)) throw new Error('Public indexing must be true or false.');
  return {
    contactEmail,
    contactHref: contactEmail ? `mailto:${contactEmail}` : undefined,
    operatorName,
    siteUrl,
    privacyHref: secureUrl(env.PMS_PUBLIC_PRIVACY_URL) ?? '/privacy',
    termsHref: secureUrl(env.PMS_PUBLIC_TERMS_URL) ?? '/terms',
    indexingEnabled: indexing === 'true' && Boolean(siteUrl),
  };
}
