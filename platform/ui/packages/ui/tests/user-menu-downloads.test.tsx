import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { UserMenu } from '../src/components/UserMenu';

it('places a real Downloads link between separators before Sign out and skips rules during keyboard navigation', async () => {
  const user = userEvent.setup();
  render(<UserMenu name="Admin" items={[
    { id: 'password', label: 'Change password' },
    { id: 'downloads', label: 'Downloads', href: '/downloads', separated: true },
    { id: 'signout', label: 'Sign out' },
  ]} />);
  await user.click(screen.getByRole('button', { name: 'Admin' }));
  expect(screen.getAllByRole('separator')).toHaveLength(2);
  const link = screen.getByRole('menuitem', { name: 'Downloads' });
  expect(link.tagName).toBe('A');
  expect(link).toHaveAttribute('href', '/downloads');
  expect(link.previousElementSibling).toHaveAttribute('role', 'separator');
  expect(link.nextElementSibling).toHaveAttribute('role', 'separator');
  await user.keyboard('{ArrowDown}');
  expect(link).toHaveFocus();
  await user.keyboard('{ArrowDown}');
  expect(screen.getByRole('menuitem', { name: 'Sign out' })).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.getByRole('button', { name: 'Admin' })).toHaveFocus();
});

it('activates a menu link with Space and restores focus', async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  render(<UserMenu name="Admin" onSelect={select} items={[
    { id: 'downloads', label: 'Downloads', href: '#downloads', separated: true },
    { id: 'signout', label: 'Sign out' },
  ]} />);
  const trigger = screen.getByRole('button', { name: 'Admin' });
  await user.click(trigger);
  await user.keyboard(' ');
  expect(select).toHaveBeenCalledWith('downloads');
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it('keeps keyboard activation aligned with focus moved by a pointer', async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  render(<UserMenu name="Admin" onSelect={select} items={[
    { id: 'password', label: 'Change password' },
    { id: 'downloads', label: 'Downloads', href: '#downloads', separated: true },
    { id: 'signout', label: 'Sign out' },
  ]} />);
  await user.click(screen.getByRole('button', { name: 'Admin' }));
  act(() => screen.getByRole('menuitem', { name: 'Downloads' }).focus());
  await user.keyboard(' ');
  expect(select).toHaveBeenCalledTimes(1);
  expect(select).toHaveBeenCalledWith('downloads');
});
