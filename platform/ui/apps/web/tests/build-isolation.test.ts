import { afterEach, expect, it, vi } from 'vitest';
import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD, PHASE_PRODUCTION_SERVER } from 'next/constants';
import config from '../next.config.mjs';

afterEach(() => vi.unstubAllEnvs());
it('keeps production builds out of the running dev server and separates review instances', () => {
  vi.stubEnv('PMS_WEB_INSTANCE', '3000');
  const main = config(PHASE_DEVELOPMENT_SERVER).distDir;
  vi.stubEnv('PMS_WEB_INSTANCE', '3124');
  expect(config(PHASE_DEVELOPMENT_SERVER).distDir).not.toBe(main);
  expect(config(PHASE_PRODUCTION_BUILD).distDir).not.toBe(main);
  expect(config(PHASE_PRODUCTION_SERVER).distDir).toBe(config(PHASE_PRODUCTION_BUILD).distDir);
});
it('rejects an instance name that escapes the app cache directory', () => {
  vi.stubEnv('PMS_WEB_INSTANCE', '../outside');
  expect(() => config(PHASE_DEVELOPMENT_SERVER)).toThrow('Invalid PMS_WEB_INSTANCE');
});
