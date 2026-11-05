export type ModelCategory =
  | 'text'
  | 'conversation'
  | 'asr'
  | 'tts'
  | 'vision'
  | 'video'
  | 'ocr'
  | 'embedding'
  | 'reranking'
  | 'image_generation'
  | 'video_generation';

export type ModelDefinition = {
  id: string;
  provider: string;
  model_key: string;
  display_name: string;
  description: string | null;
  publisher: string | null;
  model_family: string | null;
  model_version: string | null;
  categories: ModelCategory[];
  operations: string[];
  capabilities: Record<string, any>;
  adapter_status: 'available' | 'unavailable';
  /** 'retired' is only ever visible through the platform catalog view; the tenant-facing read never returns it. */
  lifecycle: 'active' | 'deprecated' | 'retired';
  version: number;
  created_at: string;
  updated_at: string;
};

export type ModelQuery = {
  q: string;
  provider: string | undefined;
  category: ModelCategory | undefined;
  /** `undefined` means "no filter" only against the platform catalog; the tenant-facing read defaults an omitted filter to 'active'. */
  lifecycle: ModelDefinition['lifecycle'] | undefined;
  adapter_status: ModelDefinition['adapter_status'] | undefined;
  sort_by: 'display_name' | 'provider' | 'created_at';
  sort_order: 'asc' | 'desc';
  limit: number;
};

export const MODEL_PAGE_LIMITS = [25, 50, 100] as const;

export const DEFAULT_MODEL_QUERY: ModelQuery = {
  q: '',
  provider: undefined,
  category: undefined,
  lifecycle: 'active',
  adapter_status: undefined,
  sort_by: 'display_name',
  sort_order: 'asc',
  limit: 25,
};

/**
 * Local preview only. Filter, sort, and slice models.
 */
export function modelPage(
  rows: readonly ModelDefinition[],
  query: ModelQuery,
  requestedPage: number
) {
  const needle = query.q.trim().slice(0, 128).toLowerCase();
  const direction = query.sort_order === 'asc' ? 1 : -1;
  const compare = (left: string | null, right: string | null) => {
    const l = left ?? '';
    const r = right ?? '';
    return l < r ? -1 : l > r ? 1 : 0;
  };

  const matches = rows.filter((row) => {
    const matchesQuery = !needle ||
      row.display_name.toLowerCase().includes(needle) ||
      row.model_key.toLowerCase().includes(needle) ||
      (row.description && row.description.toLowerCase().includes(needle));

    const matchesProvider = query.provider === undefined || row.provider === query.provider;
    const matchesCategory = query.category === undefined || row.categories.includes(query.category);
    const matchesLifecycle = query.lifecycle === undefined || row.lifecycle === query.lifecycle;
    const matchesAdapter = query.adapter_status === undefined || row.adapter_status === query.adapter_status;

    return matchesQuery && matchesProvider && matchesCategory && matchesLifecycle && matchesAdapter;
  }).sort((left, right) => {
    const primaryCompare = compare(left[query.sort_by], right[query.sort_by]);
    return direction * (primaryCompare || compare(left.id, right.id));
  });

  const limit = Math.max(1, Math.min(100, query.limit));
  const page = Math.max(0, Math.min(requestedPage, Math.ceil(matches.length / limit) - 1));
  const offset = page * limit;

  return {
    items: matches.slice(offset, offset + limit),
    total: matches.length,
    page,
    from: matches.length ? offset + 1 : 0,
    has_more: offset + limit < matches.length,
  };
}

export function deprecateModel(row: ModelDefinition, timestamp: string): ModelDefinition {
  if (row.lifecycle === 'deprecated') return row;
  return {
    ...row,
    lifecycle: 'deprecated',
    updated_at: timestamp,
    version: row.version + 1,
  };
}
