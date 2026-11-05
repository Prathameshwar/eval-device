import { afterEach, expect, it, vi } from 'vitest';
import { GET } from '../src/app/health/ready/route';

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

it.each(['http://127.0.0.1:8000/api/v1', 'http://localhost:8000/api/v1/'])(
  'accepts the selected local API without contacting it: %s', async base => {
    vi.stubEnv('PMS_API_BASE_URL', base);
    vi.stubGlobal('fetch', vi.fn());
    const response = GET(new Request('http://127.0.0.1:3000/health/ready?api_port=8000'));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ service: 'pms_web', status: 'ready' });
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    expect(fetch).not.toHaveBeenCalled();
  },
);

it.each([
  'http://127.0.0.1:8001/api/v1', 'https://example.invalid/api/v1',
  'http://127.0.0.1:8000/other',
])('rejects a UI configured for another API: %s', async base => {
  vi.stubEnv('PMS_API_BASE_URL', base);
  const response = GET(new Request('http://127.0.0.1:3000/health/ready?api_port=8000'));
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({ service: 'pms_web', status: 'not_ready', reason: 'api_mismatch' });
});

it.each(['', '0', '65536', '-1', '8000.0', '00800', 'http://other.invalid'])('rejects invalid ports: %s', async port => {
  const response = GET(new Request(`http://127.0.0.1:3000/health/ready?api_port=${encodeURIComponent(port)}`));
  expect(response.status).toBe(400);
  expect((await response.json()).reason).toBe('invalid_api_port');
});

it('redacts invalid configuration and never makes an upstream request', async () => {
  vi.stubEnv('PMS_API_BASE_URL', 'http://user:private-password@127.0.0.1:8000/api/v1');
  vi.stubGlobal('fetch', vi.fn());
  const response = GET(new Request('http://127.0.0.1:3000/health/ready?api_port=8000'));
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({ service: 'pms_web', status: 'not_ready', reason: 'invalid_api_configuration' });
  expect(fetch).not.toHaveBeenCalled();
});
