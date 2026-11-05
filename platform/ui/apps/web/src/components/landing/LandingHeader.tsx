'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';
import { ArrowRightIcon, MenuIcon } from '@pms/ui';
import { BrandLockup } from '@/components/BrandMark';
import styles from './LandingPage.module.css';

const navigation = [
  ['Platform', '#platform'],
  ['Meet Alex', '#alex'],
  ['How It Works', '#how-it-works'],
  ['FAQ', '#faq'],
  ['Contact', '#contact'],
] as const;

export function LandingHeader({ signedIn, onHome = true }: { signedIn: boolean; onHome?: boolean }) {
  const menu = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const accountHref = signedIn ? '/home' : '/login';
  const accountLabel = signedIn ? 'My Account' : 'Login';

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 64rem)');
    const header = menu.current?.closest('header');
    const landing = header?.parentElement;
    const measure = () => {
      if (header && landing) landing.style.setProperty('--landing-header-height', `${header.getBoundingClientRect().height}px`);
    };
    const observer = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(measure);
    if (header) observer?.observe(header);
    measure();
    const close = () => { if (menu.current) menu.current.open = false; };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !menu.current?.contains(event.target)) close();
    };
    desktop.addEventListener('change', close);
    document.addEventListener('pointerdown', outside);
    return () => {
      observer?.disconnect();
      landing?.style.removeProperty('--landing-header-height');
      desktop.removeEventListener('change', close);
      document.removeEventListener('pointerdown', outside);
    };
  }, []);

  return (
    <header className={styles.header} onKeyDown={(event) => {
      if (event.key === 'Escape' && menu.current?.open) {
        menu.current.open = false;
        summary.current?.focus();
      }
    }}>
      <div className={`${styles.container} ${styles.headerInner}`}>
        <Link href="/#top" className={styles.brand} aria-label="AI Evaluator home"><BrandLockup size="compact" /></Link>
        <nav className={styles.desktopNav} aria-label="Main navigation">
          {navigation.map(([label, href]) => <a key={href} href={onHome ? href : `/${href}`}>{label}</a>)}
        </nav>
        <Link href={accountHref} className={`${styles.button} ${styles.accountButton}`}>{accountLabel}<ArrowRightIcon size={16} /></Link>
        <details ref={menu} className={styles.mobileMenu}>
          <summary ref={summary} aria-label="Navigation menu"><MenuIcon size={22} /><span>Menu</span></summary>
          <nav className={styles.mobileNav} aria-label="Mobile navigation">
            {navigation.map(([label, href]) => <a key={href} href={onHome ? href : `/${href}`} onClick={() => {
              if (menu.current) menu.current.open = false;
              if (onHome) document.querySelector<HTMLElement>(href)?.focus({ preventScroll: true });
            }}>{label}</a>)}
            <Link href={accountHref} onClick={() => { if (menu.current) menu.current.open = false; }}>{accountLabel}<ArrowRightIcon size={16} /></Link>
          </nav>
        </details>
      </div>
    </header>
  );
}
