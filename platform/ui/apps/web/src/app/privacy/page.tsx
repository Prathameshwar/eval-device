import type { Metadata } from 'next';
import { PublicDocument, type DocumentSection } from '@/components/landing/PublicDocument';
import { publicAccountSignedIn } from '@/lib/public-account';
import { publicSite } from '@/lib/public-site';

export function generateMetadata(): Metadata {
  const site = publicSite();
  return { title: 'Privacy & data use', description: 'How AI Evaluator uses account, scenario, and training information.', robots: { index: site.indexingEnabled, follow: site.indexingEnabled }, ...(site.siteUrl ? { alternates: { canonical: new URL('/privacy', site.siteUrl).toString() } } : {}) };
}

const sections: readonly DocumentSection[] = [
  { id: 'scope', title: 'Your institution and this service', paragraphs: [
    'AI Evaluator supports institution-managed clinical simulation. This page explains the product’s data handling. Your institution and its deployment operator provide the deployment-specific privacy information, including their identity, processing purposes, legal basis, hosting locations, and applicable individual rights.',
    'If your institution supplies a separate privacy notice, read it alongside this information. The configuration and services selected for your deployment determine which processing features are used.',
  ] },
  { id: 'information', title: 'Information used by the platform', paragraphs: [
    'Account and organization information can include your name, email address, membership, department, and assigned permissions. Device information can include registration, configuration, status, and operational activity.',
    'Training information can include fictional patient scenarios, session details, conversation transcripts, feedback, and audio or video captured when those features are used. Use fictional case details and follow your institution’s policies before recording anyone or adding information about a real person.',
  ] },
  { id: 'purpose', title: 'Why this information is used', paragraphs: [
    'The platform uses this information to sign users in, enforce access permissions, manage scenarios and devices, coordinate sessions, provide authorized access to records, and record administrative and operational activity.',
    'Permissions limit access by organization, department, and role. Platform administration alone does not grant access to an institution’s private training media.',
  ] },
  { id: 'storage', title: 'Storage and processing services', paragraphs: [
    'Application records are stored in the deployment’s database. Media can be stored through configured private storage or the desktop companion. Depending on the selected processing configuration, services can run locally or use institution-configured cloud providers.',
    'Your institution or deployment operator can explain its enabled providers, hosting regions, data-sharing arrangements, and retention settings. This page does not specify a universal retention period because deployments can have different configurations.',
  ] },
  { id: 'browser-storage', title: 'Cookies and browser preferences', paragraphs: [
    'The application uses cookies for account sessions and the selected organization context. Sign-in cookies are protected from JavaScript access; production sessions use Secure cookies over HTTPS. A remembered sign-in can persist beyond the current browser session.',
    'The selected display theme is stored in a preference cookie and browser local storage. The theme cookie lasts up to one year. The public landing page adds no advertising or third-party analytics scripts. Hosting services may keep their own operational logs.',
  ] },
  { id: 'requests', title: 'Access, corrections, and retention questions', paragraphs: [
    'Contact your organization administrator or the privacy contact named in your institution’s notice if you need information about access, correction, deletion, retention, or other rights that apply to your records.',
    'Removing an account or changing a role does not necessarily remove records retained by an institution. Requests must be reviewed against the institution’s obligations, record ownership, and configured retention arrangements.',
  ] },
];

export default async function PrivacyPage() {
  return <PublicDocument title="Privacy & data use" lead="A clear view of the information behind your account and training workspace." sections={sections} signedIn={await publicAccountSignedIn()} site={publicSite()} />;
}
