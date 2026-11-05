import type { Metadata } from 'next';
import { ForgotPasswordForm } from '@/components/ForgotPasswordForm';

export const metadata: Metadata = {
  title: 'Reset password',
  description: 'Request a password reset link for your AI Evaluator account.',
};

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
