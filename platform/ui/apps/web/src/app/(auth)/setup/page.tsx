import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { Notice } from '@pms/ui';
import { InitialSetup } from '@/components/InitialSetup';
import { setupStatus } from '@/lib/setup';

export const metadata: Metadata = { title: 'Initial setup', robots: { index: false, follow: false } };
export const dynamic = 'force-dynamic';

export default async function SetupPage() {
  const status = await setupStatus();
  if (status && !status.required) redirect('/login');
  if (status?.available) return <InitialSetup />;
  return <section className="pms-auth__card">
    <header className="pms-auth__head"><h1 className="pms-h1">Set up your platform</h1></header>
    <Notice tone="warning" title={status ? 'Setup is not enabled yet' : 'Unable to check setup'}>
      {status ? 'Your deployment needs password sign-in and a private installation key enabled before the first administrator can be created. Contact the person managing this installation.' : 'The API is unavailable. Start the API and check its database connection, then try again.'}
    </Notice>
    <p className="pms-auth__alt"><a className="pms-link" href="/setup">Check again</a></p>
  </section>;
}
