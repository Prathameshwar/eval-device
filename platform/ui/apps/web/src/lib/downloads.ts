import 'server-only';
import { ApiError } from './api';
import { currentUser, sessionToken } from './session';
import { canDownload } from './download-access';

export type DesktopRelease = { id: 'desktop-cuda' | 'desktop-runtime' | 'desktop-cpu'; filename: string; size_bytes: number; sha256: string };

export async function downloadSession() {
  const user = await currentUser();
  if (!user) throw new ApiError(401, 'authentication_required');
  if (!canDownload(user)) throw new ApiError(403, 'permission_denied');
  const token = await sessionToken();
  if (!token) throw new ApiError(401, 'authentication_required');
  return { user, token };
}
