import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DEMO_USERS } from './fixtures/accounts';
import { ToastProvider, PermissionProvider } from '@pms/ui';

const { currentUser, redirect } = vi.hoisted(() => ({
  currentUser: vi.fn(),
  redirect: vi.fn((path: string): never => {
    throw new Error(`redirect:${path}`);
  }),
}));
vi.mock('@/lib/session', () => ({ currentUser }));
vi.mock('next/navigation', () => ({
  redirect,
  useRouter: () => ({ refresh: vi.fn() }),
}));
vi.mock('../src/lib/personal-actions', () => ({
  readPersonal: vi.fn(async () => ({
    value: {
      display_name: 'Member',
      email: 'member@example.com',
      phone: null,
      auth_method: 'local',
    },
  })),
  savePersonal: vi.fn(),
}));
vi.mock('../src/lib/model-actions', () => ({
  listModels: vi.fn(async () => ({
    value: { items: [], total: 0, has_more: false, next_cursor: null },
  })),
}));
vi.mock('../src/lib/people-actions', () => ({
  listPeople: vi.fn(async () => ({
    value: { items: [], total: 0, has_more: false, next_cursor: null },
  })),
  peopleDepartments: vi.fn(async () => ({ value: [] })),
}));
vi.mock('../src/lib/subscription-actions', () => ({
  listSubscriptions: vi.fn(async () => ({
    value: { items: [], total: 0, has_more: false, next_cursor: null },
  })),
  subscriptionPlans: vi.fn(async () => ({ value: [] })),
}));
vi.mock('../src/lib/tenant-actions', () => ({
  activeTenantOptions: vi.fn(async () => [{ id: '12345678-1234-4234-8234-123456789012', name: 'Example tenant' }]),
}));
vi.mock('../src/lib/platform-options-actions', () => ({
  readPlatformOptions: vi.fn(async () => ({
    value: {
      configuration_version: 1,
      display_name: 'AI Evaluator',
      registration_mode: 'invite_only',
      languages: [{ code: 'en', name: 'English', speech_locale: 'en-IN', is_active: true }],
      enabled_providers: [],
      maintenance_mode: false,
    },
  })),
  savePlatformOptions: vi.fn(),
}));
import Settings from '../src/app/(console)/settings/page';
import PlatformOptions from '../src/app/(console)/platform-options/page';
import Models from '../src/app/(console)/models/page';
import Licenses from '../src/app/(console)/licenses/page';
import Administrators from '../src/app/(console)/users/page';
import LlmConnections from '../src/app/(console)/llm-connections/page';
import { ModelDirectoryProvider } from '../src/components/ModelDirectoryProvider';
import { DEMO_MODELS } from '../src/data/models';

const models = () => Models();
const routes = [Settings, PlatformOptions, models, Licenses, Administrators, () => LlmConnections()];
const platform = {
  ...DEMO_USERS.find((user) => user.role === 'platform_admin')!,
  contextId: 'platform',
};
const tenantAdmin = {
  ...DEMO_USERS.find((user) => user.role === 'org_admin')!,
  contextId: '12345678-1234-4234-8234-123456789012',
};
const tenantUser = DEMO_USERS.find((user) => user.role === 'org_user')!;

describe('Settings routes', () => {
  it.each(routes)('requires a session before rendering a settings route', async (page) => {
    currentUser.mockResolvedValue(undefined);
    await expect(page()).rejects.toThrow('redirect:/login');
  });

  it.each(routes)('refuses direct access without a grant', async (page) => {
    currentUser.mockResolvedValue({ ...platform, permissions: [] });
    await expect(page()).rejects.toThrow('redirect:/home');
  });

  it.each([
    [PlatformOptions, 'Platform options'],
    [models, 'Models'],
    [Licenses, 'Subscriptions'],
    [Administrators, 'Users & administrators'],
  ] as const)('gives an authorized destination a Settings return link', async (page, title) => {
    currentUser.mockResolvedValue(platform);
    const element = await page();
    if (title === 'Models') {
      render(
        <PermissionProvider permissions={platform.permissions}>
          <ToastProvider>
            <ModelDirectoryProvider initialRows={DEMO_MODELS}>{element}</ModelDirectoryProvider>
          </ToastProvider>
        </PermissionProvider>,
      );
    } else if (title === 'Users & administrators') {
      render(<ToastProvider>{element}</ToastProvider>);
    } else {
      render(element);
    }
    if (title === 'Platform options') await screen.findByDisplayValue('AI Evaluator');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      title,
    );
    const back = screen.getByRole('navigation', { name: 'Back navigation' });
    expect(within(back).getByRole('link', { name: 'Back to settings' })).toHaveAttribute('href', '/settings');
  });

  it('lets a category reader reach the hub without settings-manage', async () => {
    currentUser.mockResolvedValue({
      ...platform,
      permissions: ['platform.users.read'],
    });
    render(await Settings());
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/home');
    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Users & administrators' })).toBeInTheDocument();
    await expect(models()).rejects.toThrow('redirect:/home');
  });

  it('opens platform options for a settings reader and enables editing only with manage permission', async () => {
    currentUser.mockResolvedValue({ ...platform, permissions: ['platform.settings.read'] });
    expect((await PlatformOptions()).props.canManage).toBe(false);
    currentUser.mockResolvedValue(platform);
    expect((await PlatformOptions()).props.canManage).toBe(true);
  });

  it('keeps platform options out of tenant roles and tenant contexts', async () => {
    currentUser.mockResolvedValue({ ...tenantAdmin, permissions: platform.permissions });
    await expect(PlatformOptions()).rejects.toThrow('redirect:/home');
    currentUser.mockResolvedValue({ ...platform, contextId: tenantAdmin.contextId });
    await expect(PlatformOptions()).rejects.toThrow('redirect:/home');
  });

  it('keeps model management restricted while preserving tenant subscription view', async () => {
    currentUser.mockResolvedValue(tenantAdmin);
    await expect(models()).rejects.toThrow('redirect:/home');
    expect((await Licenses()).props.organizationId).toBe(tenantAdmin.contextId);
    await expect(Administrators()).rejects.toThrow('redirect:/home');
  });

  it('redirects the retired LLM page to Models only for Platform Admin', async () => {
    currentUser.mockResolvedValue(platform);
    await expect(LlmConnections())
      .rejects.toThrow('redirect:/models');
    currentUser.mockResolvedValue(tenantUser);
    await expect(LlmConnections()).rejects.toThrow('redirect:/home');
    currentUser.mockResolvedValue({
      ...tenantAdmin,
      contextId: 'tenant-context',
    });
    await expect(LlmConnections()).rejects.toThrow('redirect:/home');
  });

  it('keeps personal settings while denying management routes to tenant users', async () => {
    currentUser.mockResolvedValue(tenantUser);
    render(await Settings());
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Personal settings');
    expect(screen.queryByRole('region', { name: 'Settings sections' })).not.toBeInTheDocument();
    await expect(models()).rejects.toThrow('redirect:/home');
    await expect(Licenses()).rejects.toThrow('redirect:/home');
    await expect(Administrators()).rejects.toThrow('redirect:/home');
  });
});
