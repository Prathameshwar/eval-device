import Link from 'next/link';
import { BrandLockup } from '@/components/BrandMark';
import type { PublicSite } from '@/lib/public-site';
import styles from './LandingPage.module.css';

export function LandingFooter({ signedIn, site }: { signedIn: boolean; site: PublicSite }) {
  return (
    <footer className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.footerGrid}>
          <div>
            <Link href="/#top" className={styles.brand} aria-label="AI Evaluator home"><BrandLockup size="compact" /></Link>
            <p className={styles.footerDescription}>Healthcare simulation,<br />thoughtfully connected.</p>
            {site.operatorName && <p className={styles.operatorName}>{site.operatorName}</p>}
          </div>
          <nav aria-label="Footer explore">
            <span className={styles.footerLabel}>Explore</span>
            <Link href="/#platform">The platform</Link>
            <Link href="/#alex">Meet Alex</Link>
            <Link href="/#how-it-works">How it works</Link>
          </nav>
          <nav aria-label="Footer contact and account">
            <span className={styles.footerLabel}>Get in touch</span>
            {site.contactHref && <a href={site.contactHref}>{site.contactEmail}</a>}
            <Link href={signedIn ? '/home' : '/login'}>{signedIn ? 'My Account' : 'Login'}</Link>
            <Link href="/#faq">Frequently asked questions</Link>
          </nav>
        </div>
        <div className={styles.footerBottom}>
          <span>© {new Date().getFullYear()} {site.operatorName ?? 'AI Evaluator'}</span>
          <nav className={styles.legalLinks} aria-label="Legal information">
            <a href={site.privacyHref}>Privacy & data use</a>
            <a href={site.termsHref}>Terms of use</a>
          </nav>
        </div>
      </div>
    </footer>
  );
}
