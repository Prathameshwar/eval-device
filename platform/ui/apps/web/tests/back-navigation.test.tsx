import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { BackNavigation } from '../src/components/BackNavigation';

it('provides a keyboard-accessible link to an explicit parent', async () => {
  render(<BackNavigation href="/models?tab=catalog" label="Back to models" />);
  const link = screen.getByRole('link', { name: 'Back to models' });
  expect(link).toHaveAttribute('href', '/models?tab=catalog');
  await userEvent.setup().tab();
  expect(link).toHaveFocus();
});

it('uses a non-submitting button for guarded returns and prevents busy activation', async () => {
  const onBack = vi.fn();
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
  const { rerender } = render(<form onSubmit={submit}><BackNavigation label="Back to profiles" onBack={onBack} /></form>);
  const visitor = userEvent.setup();
  await visitor.tab();
  await visitor.keyboard('{Enter}');
  expect(onBack).toHaveBeenCalledTimes(1);
  expect(submit).not.toHaveBeenCalled();
  rerender(<BackNavigation label="Back to profiles" onBack={onBack} disabled />);
  await visitor.click(screen.getByRole('button', { name: 'Back to profiles' }));
  expect(onBack).toHaveBeenCalledTimes(1);
});
