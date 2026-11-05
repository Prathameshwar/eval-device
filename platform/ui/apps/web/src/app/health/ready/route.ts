import { apiBaseUrl } from '@/lib/api';

export const dynamic = 'force-dynamic';

/** Local launcher identity/configuration check. Never fetch or reveal the configured URL. */
export function GET(request: Request): Response {
  const port = new URL(request.url).searchParams.get('api_port') ?? '';
  const reply = (status: number, reason?: string) => Response.json(
    { service: 'pms_web', status: status === 200 ? 'ready' : 'not_ready', ...(reason ? { reason } : {}) },
    { status, headers: { 'Cache-Control': 'no-store' } },
  );
  if (!/^[1-9]\d{0,4}$/.test(port) || Number(port) > 65535) return reply(400, 'invalid_api_port');
  try {
    const api = new URL(apiBaseUrl());
    if (
      api.protocol !== 'http:' ||
      !['127.0.0.1', 'localhost'].includes(api.hostname) ||
      (api.port || '80') !== port ||
      api.pathname !== '/api/v1'
    ) return reply(503, 'api_mismatch');
  } catch {
    return reply(503, 'invalid_api_configuration');
  }
  return reply(200);
}
