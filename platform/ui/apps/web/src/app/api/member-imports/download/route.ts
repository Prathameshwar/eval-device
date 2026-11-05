import { ApiError } from '@/lib/api';
import { resourceId } from '@/lib/console-api';
import { importError } from '@/lib/member-import-actions';
import { importOptions, type ImportOptions } from '@/lib/member-imports';
import { importRequest } from '@/lib/member-import-transport';

export async function GET(request: Request) {
  try {
    const query = new URL(request.url).searchParams;
    const context = resourceId(query.get('context') ?? '');
    const kind = query.get('kind');
    let suffix: string;
    if (kind === 'template') {
      const options = { role: query.get('role'), auth_method: query.get('auth_method'),
        department_id: query.get('department_id') ?? '' } as ImportOptions;
      if (options.department_id) resourceId(options.department_id);
      suffix = '/template?' + importOptions(options);
    } else if (kind === 'errors' || kind === 'results' || kind === 'passwords') {
      suffix = '/' + resourceId(query.get('id') ?? '') + '/report?' +
        (kind === 'passwords' ? 'passwords_only=true' : 'errors_only=' + (kind === 'errors'));
    } else throw new ApiError(422, 'invalid_request');
    const upstream = await importRequest(context, suffix);
    return new Response(await upstream.arrayBuffer(), { headers: {
      'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'Content-Disposition': 'attachment; filename="member-import-' + kind + '.xlsx"',
      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    } });
  } catch (error) {
    return Response.json({ error: await importError(error) },
      { status: error instanceof ApiError ? error.status : 422, headers: { 'Cache-Control': 'no-store' } });
  }
}
