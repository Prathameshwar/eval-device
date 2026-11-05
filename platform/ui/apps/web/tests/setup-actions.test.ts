import { afterEach, describe, expect, it, vi } from 'vitest';
import { completeInitialSetup, verifyInstallationKey } from '../src/lib/setup-actions';

afterEach(() => vi.unstubAllGlobals());

describe('Setup server actions', () => {
  it('forwards only allowed account fields and never echoes credentials', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ completed: true }), { status: 201 }));
    vi.stubGlobal('fetch', fetcher);
    const details = { display_name: ' Ada ', email: ' ada@example.com ', password: 'test-private-passphrase', installation_key: 'test-private-key', platform_role: 'other-role' };
    expect(await completeInitialSetup(details)).toEqual({ completed: true });
    const [, options] = fetcher.mock.calls[0]!;
    expect(JSON.parse(options.body)).toEqual({ display_name: 'Ada', email: 'ada@example.com', password: details.password, installation_key: details.installation_key });
    expect(options.cache).toBe('no-store');
  });

  it('rejects malformed inputs before contacting the API', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    expect(await verifyInstallationKey('')).toHaveProperty('error');
    expect(await verifyInstallationKey('x'.repeat(513))).toHaveProperty('error');
    expect(await completeInitialSetup(null as never)).toHaveProperty('error');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('keeps rejected installation text on the installation step', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'invalid_request' },
    }), { status: 422 })));
    expect(await verifyInstallationKey('invalid installation text')).toEqual({
      error: 'Enter a valid installation key.', code: 'invalid_setup_key',
    });
  });

  it('maps setup failures without exposing API details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
      code: 'invalid_setup_key', message: 'private response value', details: 'private diagnostic',
    } }), { status: 403 })));
    const result = await verifyInstallationKey('my private input key');
    expect(result.code).toBe('invalid_setup_key');
    expect(result.error).toMatch(/incorrect/);
    for (const secret of ['private response value', 'private diagnostic', 'my private input key']) {
      expect(JSON.stringify(result)).not.toContain(secret);
    }
  });
});
