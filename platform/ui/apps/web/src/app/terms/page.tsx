import type { Metadata } from 'next';
import { PublicDocument, type DocumentSection } from '@/components/landing/PublicDocument';
import { publicAccountSignedIn } from '@/lib/public-account';
import { publicSite } from '@/lib/public-site';

export function generateMetadata(): Metadata {
  const site = publicSite();
  return { title: 'Terms of use', description: 'Responsible use of the AI Evaluator clinical simulation workspace.', robots: { index: site.indexingEnabled, follow: site.indexingEnabled }, ...(site.siteUrl ? { alternates: { canonical: new URL('/terms', site.siteUrl).toString() } } : {}) };
}

const sections: readonly DocumentSection[] = [
  { id: 'educational-use', title: 'Educational simulation', paragraphs: [
    'AI Evaluator is a workspace for clinical simulation, scenario management, and training coordination. Alex is a fictional simulated patient. Scenarios and generated conversations are educational material, not instructions for diagnosing or treating a real patient.',
    'Use the platform within the scope approved by your institution. Clinical content and training activities require appropriate educator review.',
  ] },
  { id: 'accounts', title: 'Accounts and access', paragraphs: [
    'Use your assigned account and keep its credentials private. Your institution assigns roles and access to organization or department information. Do not share an account, bypass permissions, or access another institution’s records without authorization.',
    'Contact your organization administrator to request an invitation, correct your access, or report suspected account misuse.',
  ] },
  { id: 'content', title: 'Scenarios and recordings', paragraphs: [
    'Only upload or create content you are authorized to use. Use fictional patient details for simulation and follow institutional requirements concerning confidentiality, recording permissions, and intellectual property.',
    'Check scenario facts, language, and starting vitals before submitting material for review. Published scenarios preserve the version selected for a training session; later edits do not automatically change a session already using that version.',
  ] },
  { id: 'ai-output', title: 'AI output and educator judgment', paragraphs: [
    'AI-generated responses can be incomplete or inaccurate. Review them in the context of the authored scenario and your training objectives. A simulated conversation does not establish clinical competence by itself.',
    'Educators remain responsible for interpreting the available records and deciding how they are used in teaching or assessment.',
  ] },
  { id: 'setup', title: 'Training setup and availability', paragraphs: [
    'Available functions depend on your role, the deployment configuration, approved scenarios, and the devices or companion software used by your institution. Desktop practice and browser administration have different responsibilities.',
    'Confirm your setup with the responsible simulation team. The public website does not promise a specific hardware configuration, response time, language accuracy, or uninterrupted service.',
  ] },
  { id: 'institutional-terms', title: 'Institutional arrangements', paragraphs: [
    'These usage guidelines accompany any applicable agreement between your institution and its service provider, together with your institution’s policies. They do not set pricing, subscription periods, service levels, or deployment-specific legal arrangements.',
    'For those details, consult the responsible institution or deployment operator. An institution can provide its own approved terms through the public website’s terms link.',
  ] },
];

export default async function TermsPage() {
  return <PublicDocument title="Terms of use" lead="Practical guidelines for a responsible clinical simulation workspace." sections={sections} signedIn={await publicAccountSignedIn()} site={publicSite()} />;
}
