import Link from 'next/link';
import {
  ActivityIcon, ArrowRightIcon, BookIcon, CalendarIcon,
  CustomersIcon, DocumentIcon, EditIcon, MonitorIcon, ReportsIcon, SettingsIcon,
} from '@pms/ui';
import { publicSite, type PublicSite } from '@/lib/public-site';
import { LandingHeader } from './LandingHeader';
import { LandingFooter } from './LandingFooter';
import styles from './LandingPage.module.css';

const capabilities = [
  { icon: BookIcon, title: 'Patient scenarios', body: 'Create a clear clinical context with patient profiles, symptoms, history, and starting vitals.' },
  { icon: CalendarIcon, title: 'Training sessions', body: 'Bring reviewed scenarios and your training setup together for the next simulation session.' },
  { icon: DocumentIcon, title: 'Session records', body: 'Review saved conversations and available session media with your team.' },
  { icon: MonitorIcon, title: 'Teams & devices', body: 'Manage your institution’s people, roles, and connected devices in one workspace.' },
];

const workflow = [
  { icon: EditIcon, title: 'Prepare', body: 'Build and review a patient scenario in the web platform, with the clinical context your session needs.' },
  { icon: ActivityIcon, title: 'Simulate', body: 'Choose the reviewed scenario and prepare your training setup. Desktop practice runs in the companion app.' },
  { icon: ReportsIcon, title: 'Review', body: 'Use saved conversations and available session records to discuss the practice session with your team.' },
];

const audiences = [
  { icon: BookIcon, title: 'Clinical educators', body: 'Shape clinical scenarios around the patient presentation and history you want learners to explore.' },
  { icon: CustomersIcon, title: 'Simulation teams', body: 'Coordinate scenarios, session setup, and connected devices for your simulation activities.' },
  { icon: SettingsIcon, title: 'Institution administrators', body: 'Organize people, departments, and permissions within your institution’s workspace.' },
];

const questions = [
  ['What does AI Evaluator help us manage?', 'AI Evaluator brings patient scenario authoring, training session coordination, session records, and organization administration into one platform. Available actions depend on your assigned role.'],
  ['Who is Alex?', 'Alex is a fictional patient character for clinical simulation. The selected scenario defines the patient’s presentation, symptoms, history, background, and starting vitals.'],
  ['Can educators create their own scenarios?', 'Authorized educators can author scenarios and use the review and publication workflow. Training uses a published version of the scenario.'],
  ['What runs in the browser and what runs on the desktop?', 'The web platform manages scenarios, organization settings, and device training sessions. Patient practice takes place in the desktop companion. Your training setup determines the required devices and configuration.'],
  ['How do I access my institution’s workspace?', 'Use Login with your organization account. If you need an invitation or a different role, speak with your institution’s administrator.'],
];

export function LandingPage({ signedIn, site = publicSite({}) }: { signedIn: boolean; site?: PublicSite }) {
  const accountHref = signedIn ? '/home' : '/login';
  return (
    <div className={styles.landing} id="top">
      <a className={styles.skipLink} href="#main">Skip to content</a>
      <LandingHeader signedIn={signedIn} />
      <main id="main" tabIndex={-1}>
        <section className={styles.hero} aria-labelledby="hero-heading">
          <div className={`${styles.container} ${styles.heroGrid}`}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}><span className={styles.eyebrowDot} />Healthcare simulation, thoughtfully connected</p>
              <h1 id="hero-heading">Bring clinical<br className={styles.desktopBreak} /> learning <span>to life.</span></h1>
              <p className={styles.lead}>Prepare patient scenarios, coordinate simulation sessions, and keep training records organized with AI Evaluator.</p>
              <div className={styles.actions}>
                <a href="#platform" className={`${styles.button} ${styles.primary}`}>Explore the Platform<ArrowRightIcon size={18} /></a>
                <a href="#contact" className={`${styles.button} ${styles.secondary}`}>Contact Us</a>
              </div>
              <p className={styles.heroNote}>For educators. For simulation teams. For your institution.</p>
            </div>
            <figure className={styles.heroVisual}>
              <img
                className={styles.heroImage}
                src="/landing/alex-hero.webp"
                srcSet="/landing/alex-hero-small.webp 768w, /landing/alex-hero.webp 1280w"
                sizes="(max-width: 767px) min(100vw - 40px, 480px), (max-width: 1023px) 48vw, 580px"
                width={1280} height={1200} fetchPriority="high"
                alt="Alex, a fictional patient, alongside the AI Evaluator scenario workspace showing sample patient details."
              />
              <figcaption className={styles.visualCaption}><span className={styles.captionLine} />Fictional patient. Real platform preview.</figcaption>
            </figure>
          </div>
        </section>

        <section id="platform" tabIndex={-1} className={styles.section} aria-labelledby="platform-heading">
          <div className={styles.container}>
            <div className={styles.sectionHeading}><p className={styles.eyebrow}>The platform</p><h2 id="platform-heading">Your simulation workflow,<br />in one place.</h2><p>A workspace for patient scenarios, training sessions, and the teams that run them.</p></div>
            <div className={styles.capabilityGrid}>{capabilities.map(({ icon: Icon, title, body }) => <article className={styles.card} key={title}><span className={styles.iconBox}><Icon size={24} /></span><h3>{title}</h3><p>{body}</p></article>)}</div>
          </div>
        </section>

        <section id="alex" tabIndex={-1} className={`${styles.section} ${styles.alexSection}`} aria-labelledby="alex-heading">
          <div className={`${styles.container} ${styles.alexGrid}`}>
            <figure className={styles.alexVisual}>
              <img
                className={styles.alexImage}
                src="/landing/alex-clinical.webp"
                srcSet="/landing/alex-clinical-small.webp 768w, /landing/alex-clinical.webp 1200w"
                sizes="(max-width: 767px) calc(100vw - 40px), (max-width: 1023px) 44vw, 560px"
                width={1200} height={800} loading="lazy" decoding="async"
                alt="Alex seated beside a bed in a bright, uncluttered clinical simulation room."
              />
              <figcaption className={styles.alexVisualFoot}><strong>Alex</strong><span>Fictional simulated patient</span></figcaption>
            </figure>
            <div className={styles.alexCopy}><p className={styles.eyebrow}>Meet Alex</p><h2 id="alex-heading">A patient story.<br />A place to begin.</h2><p className={styles.lead}>Meet Alex, your fictional simulated patient for clinical learning.</p><p>Educators define the scenario’s presentation, symptoms, history, background, and starting vitals, giving each session a clear clinical context.</p><ul className={styles.alexPoints}><li><span />A defined patient presentation</li><li><span />History and background with context</li><li><span />A reviewed scenario for training</li></ul><a href="#how-it-works" className={styles.textLink}>See how it comes together<ArrowRightIcon size={18} /></a></div>
          </div>
        </section>

        <section id="how-it-works" tabIndex={-1} className={styles.section} aria-labelledby="workflow-heading">
          <div className={styles.container}><div className={`${styles.sectionHeading} ${styles.centered}`}><p className={styles.eyebrow}>A clear path</p><h2 id="workflow-heading">Prepare. Simulate. Review.</h2><p>Bring structure to the session, from the first scenario detail to the conversation afterward.</p></div><ol className={styles.workflowGrid}>{workflow.map(({ icon: Icon, title, body }, index) => <li className={styles.workflowStep} key={title}><div className={styles.stepTop}><span className={styles.iconBox}><Icon size={24} /></span><span className={styles.stepNumber}>0{index + 1}</span></div><h3>{title}</h3><p>{body}</p></li>)}</ol></div>
        </section>

        <section id="audience" tabIndex={-1} className={`${styles.section} ${styles.audienceSection}`} aria-labelledby="audience-heading">
          <div className={styles.container}><div className={styles.sectionHeading}><p className={styles.eyebrow}>Built around your team</p><h2 id="audience-heading">For the people behind<br />clinical training.</h2></div><div className={styles.audienceGrid}>{audiences.map(({ icon: Icon, title, body }) => <article className={styles.audienceCard} key={title}><span className={styles.iconBox}><Icon size={24} /></span><h3>{title}</h3><p>{body}</p></article>)}</div></div>
        </section>

        <section id="faq" tabIndex={-1} className={styles.section} aria-labelledby="faq-heading">
          <div className={`${styles.container} ${styles.faqGrid}`}><div className={styles.sectionHeading}><p className={styles.eyebrow}>Good to know</p><h2 id="faq-heading">Before you<br />get started.</h2><p>A few practical answers about the platform, Alex, and your workspace.</p></div><div className={styles.faqList}>{questions.map(([question, answer]) => <details className={styles.faqItem} key={question}><summary>{question}<span className={styles.faqPlus} aria-hidden="true" /></summary><p>{answer}</p></details>)}</div></div>
        </section>

        <section id="contact" tabIndex={-1} className={styles.contactSection} aria-labelledby="contact-heading">
          <div className={styles.container}>
            <div className={styles.contactPanel}>
              <div>
                <p className={styles.eyebrow}>Your next session starts here</p>
                <h2 id="contact-heading">Explore AI Evaluator<br />for your institution.</h2>
                <p>{site.contactHref
                  ? 'Tell us about your simulation workflow, your educators, and the training experience you want to create.'
                  : 'Explore AI Evaluator with your institution. Your organization administrator can help you with account access and your training setup.'}</p>
              </div>
              <div className={styles.contactActions}>
                {site.contactHref
                  ? <a href={site.contactHref} className={`${styles.button} ${styles.lightButton}`}>Contact Us<ArrowRightIcon size={18} /></a>
                  : <Link href={accountHref} className={`${styles.button} ${styles.lightButton}`}>{signedIn ? 'Open your workspace' : 'Access your account'}<ArrowRightIcon size={18} /></Link>}
                {site.contactEmail && <a href={site.contactHref} className={styles.contactLink}>{site.contactEmail}<ArrowRightIcon size={16} /></a>}
                <Link className={styles.contactLink} href={accountHref}>{signedIn ? 'Open your workspace' : 'Already have an account? Login'}<ArrowRightIcon size={16} /></Link>
              </div>
            </div>
          </div>
        </section>
      </main>
      <LandingFooter signedIn={signedIn} site={site} />
    </div>
  );
}
