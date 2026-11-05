import { ApiError } from './api';
/** The API supplies locations/types only. Never render rejected inputs or provider payloads. */
export function inputIssues(error: unknown): string {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return '';
  return error.details
    .slice(0, 12)
    .map((item) => {
      if (!item || typeof item !== 'object') return '';
      const path = Array.isArray(item.path) ? item.path : Array.isArray(item.location) ? item.location : null;
      if (!path || !path.every((p: unknown) => typeof p === 'string' || typeof p === 'number')) return '';
      const name = path
        .filter(
          (p: string | number) =>
            p !== 'body' &&
            !['CategoryInput', 'PatientInput', 'CaseInput', 'ScenarioDraftV2', 'ScenarioDraftV3'].includes(
              String(p),
            ),
        )
        .join('.');
      const types: Record<string, string> = {
        missing: 'Required',
        string_too_short: 'Enter a longer value',
        string_too_long: 'Shorten this value',
        string_pattern_mismatch: 'Use the required format',
        greater_than: 'Value is too small',
        greater_than_equal: 'Value is too small',
        less_than_equal: 'Value is too large',
        int_type: 'Enter a whole number',
        value_error: 'Check this field',
        too_long: 'Too many entries',
        extra_forbidden: 'Unsupported field',
      };
      const description =
        typeof item.message === 'string' ? item.message : (types[item.type] ?? 'Check this value');
      return name + ': ' + description;
    })
    .filter(Boolean)
    .join('; ');
}
