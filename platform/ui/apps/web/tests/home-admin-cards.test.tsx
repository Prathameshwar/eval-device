import { render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import HomePage from '../src/app/(console)/home/page';
import { currentUser } from '../src/lib/session';
import { loadHome } from '../src/lib/home-api';
import { ROLE_PERMISSIONS } from '../src/lib/roles';

vi.mock('../src/lib/session', () => ({ currentUser: vi.fn() }));
vi.mock('../src/lib/home-api', () => ({ loadHome: vi.fn() }));

it('renders only clinical cards for the tenant administrator without loading operational stats', async () => {
  vi.mocked(currentUser).mockResolvedValue({
    id: 'admin', name: 'Alex', email: 'alex@example.com', role: 'org_admin',
    contextId: 'tenant', tenant: { name: 'Tenant', code: 'TEN' },
    permissions: ROLE_PERMISSIONS.org_admin,
  });
  render(await HomePage());
  expect(vi.mocked(loadHome)).not.toHaveBeenCalled();
  expect(within(screen.getByRole('region', { name: 'Clinical content' })).getAllByRole('link')
    .map(link => link.getAttribute('href'))).toEqual([
    '/scenarios',
  ]);
  expect(screen.queryByText('Active members')).not.toBeInTheDocument();
});
