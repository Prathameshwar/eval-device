import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { LoginForm } from '@/components/LoginForm';
import { currentUser } from '@/lib/session';
import { setupStatus } from '@/lib/setup';

export const metadata: Metadata = {
  title: 'Sign in',
  description: 'Sign in to AI Evaluator with your organisation account.',
};

/**
 * A server component that renders one client component: the metadata above cannot be exported
 * from a `'use client'` module, and the form needs state.
 *
 * Someone already signed in is sent to the console rather than shown a form they do not need —
 * and, more usefully, the browser's back button after signing in does not land on a sign-in
 * screen that appears to have forgotten them.
 */
export default async function LoginPage() {
  if (await currentUser()) redirect('/home');
  if ((await setupStatus(2000))?.required) redirect('/setup');
  return <LoginForm />;
}
