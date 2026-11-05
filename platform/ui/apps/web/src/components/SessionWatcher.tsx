'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { checkSession } from '@/lib/actions';

const CHECK_INTERVAL_MS = 60_000;

/** Server authentication still guards every route; this catches expiry on an already open page. */
export function SessionWatcher() {
  const router = useRouter();

  useEffect(() => {
    let active = true;
    let checking = false;
    async function check() {
      if (!active || checking || document.visibilityState === 'hidden') return;
      checking = true;
      try {
        const status = await checkSession();
        if (active && status === 'expired') router.replace('/login');
      } catch {
        // The next interval or focus check can retry a transient web server failure.
      } finally {
        checking = false;
      }
    }
    function onFocus() { void check(); }
    function onVisibility() {
      if (document.visibilityState === 'visible') void check();
    }
    const timer = window.setInterval(() => void check(), CHECK_INTERVAL_MS);
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [router]);

  return null;
}
