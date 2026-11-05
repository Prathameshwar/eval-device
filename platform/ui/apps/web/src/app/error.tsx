'use client';

import Link from 'next/link';
import { Button, Notice } from '@pms/ui';

export default function AccountServiceError({ reset }: { error: Error; reset: () => void }) {
  return <main className="pms-auth__card">
    <Notice tone="danger" title="Unable to load this page">The service may be temporarily unavailable. Please try again.</Notice>
    <Button onClick={reset}>Try again</Button>
    <p><Link className="pms-link" href="/login">Sign in</Link></p>
  </main>;
}
