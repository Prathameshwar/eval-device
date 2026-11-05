import Link from 'next/link';
import { ArrowRightIcon } from '@pms/ui';
import type { PublicSite } from '@/lib/public-site';
import { LandingHeader } from './LandingHeader';
import { LandingFooter } from './LandingFooter';
import styles from './LandingPage.module.css';

export type DocumentSection = { id: string; title: string; paragraphs: readonly string[] };

export function PublicDocument({ title, lead, sections, signedIn, site }: {
  title: string;
  lead: string;
  sections: readonly DocumentSection[];
  signedIn: boolean;
  site: PublicSite;
}) {
  return (
    <div className={styles.landing}>
      <a className={styles.skipLink} href="#main">Skip to content</a>
      <LandingHeader signedIn={signedIn} onHome={false} />
      <main id="main" tabIndex={-1} className={styles.documentMain}>
        <div className={styles.container}>
          <Link href="/" className={styles.textLink}>Back to AI Evaluator<ArrowRightIcon size={16} /></Link>
          <div className={styles.documentHeading}>
            <p className={styles.eyebrow}>AI Evaluator</p>
            <h1>{title}</h1>
            <p className={styles.lead}>{lead}</p>
            <p className={styles.documentDate}>Updated 8 October 2026</p>
          </div>
          <div className={styles.documentGrid}>
            <nav className={styles.documentNav} aria-label="On this page">
              <span className={styles.footerLabel}>On this page</span>
              {sections.map(section => <a href={`#${section.id}`} key={section.id}>{section.title}</a>)}
            </nav>
            <article className={styles.documentBody} aria-label={title}>
              {sections.map(section => (
                <section id={section.id} key={section.id} aria-labelledby={`${section.id}-heading`}>
                  <h2 id={`${section.id}-heading`}>{section.title}</h2>
                  {section.paragraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
                </section>
              ))}
              <section aria-labelledby="document-contact-heading">
                <h2 id="document-contact-heading">Questions or requests</h2>
                <p>For account access or requests concerning your institution’s training records, start with your organization administrator.</p>
                {site.contactHref && <p>For product enquiries, contact {site.operatorName ?? 'the AI Evaluator team'} at <a href={site.contactHref}>{site.contactEmail}</a>.</p>}
                {!site.contactHref && <p>Your institution can identify the operator and the contact responsible for its deployment.</p>}
              </section>
            </article>
          </div>
        </div>
      </main>
      <LandingFooter signedIn={signedIn} site={site} />
    </div>
  );
}
