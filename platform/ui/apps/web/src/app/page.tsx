import type { Metadata } from 'next';
import { LandingPage } from '@/components/landing/LandingPage';
import { publicAccountSignedIn } from '@/lib/public-account';
import { publicSite } from '@/lib/public-site';

export function generateMetadata(): Metadata {
  const site = publicSite();
  const title = 'AI Evaluator · Healthcare simulation, thoughtfully connected';
  const description = 'Prepare patient scenarios, coordinate simulation sessions, and keep training records organized with AI Evaluator.';
  return {
    title: { absolute: title },
    description,
    robots: { index: site.indexingEnabled, follow: site.indexingEnabled },
    ...(site.siteUrl ? { metadataBase: new URL(site.siteUrl), alternates: { canonical: site.siteUrl } } : {}),
    openGraph: { title, description, siteName: 'AI Evaluator', type: 'website', ...(site.siteUrl ? { url: site.siteUrl } : {}) },
    twitter: { card: 'summary_large_image', title, description },
  };
}

/** Public information stays available when the account service is temporarily unavailable. */
export default async function Home() {
  return <LandingPage signedIn={await publicAccountSignedIn()} site={publicSite()} />;
}
