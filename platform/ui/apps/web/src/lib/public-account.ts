import 'server-only';
import { ApiError } from './api';
import { currentUser } from './session';

/** Account availability affects the link, not access to public product information. */
export async function publicAccountSignedIn(): Promise<boolean> {
  try {
    return Boolean(await currentUser());
  } catch (error) {
    if (error instanceof ApiError && error.status >= 500) return false;
    throw error;
  }
}
