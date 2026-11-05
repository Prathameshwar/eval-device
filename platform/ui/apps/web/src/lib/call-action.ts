import type { ApiResult } from './directory-api';
/** A transport interruption must not leave a form pending or silently retry a write. */
export async function callAction<T>(request: () => Promise<ApiResult<T>>): Promise<ApiResult<T>> {
  try {
    return await request();
  } catch {
    return {
      error: 'The request could not be confirmed. Reload the record before retrying.',
    };
  }
}
