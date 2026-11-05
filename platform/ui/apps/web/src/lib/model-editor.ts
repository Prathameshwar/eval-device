import type { ModelDefinition, ModelCategory } from './model-directory';

export type ModelDraft = {
  provider: string;
  model_key: string;
  display_name: string;
  description: string;
  publisher: string;
  model_family: string;
  model_version: string;
  categories: ModelCategory[];
  operations: string[];
  adapter_status: 'available' | 'unavailable';
  lifecycle: 'active' | 'deprecated';
};

export type ModelField = 'model_key' | 'display_name' | 'description' | 'publisher' | 'model_family' | 'model_version';
export type ModelErrors = Partial<Record<ModelField | 'categories' | 'operations' | 'provider', string>>;

export const MODEL_FIELD_LIMITS = {
  model_key: 160,
  display_name: 256,
  description: 4000,
  publisher: 160,
  model_family: 160,
  model_version: 160,
} as const;

/**
 * The API requires a non-empty `operations` list but the editor exposes no free-text control for
 * it: operation identifiers are an internal routing detail, not something an administrator should
 * hand-type. Each capability category maps to the operation identifier used elsewhere in the API
 * (see `RunCreate.operation`), so the set a model is registered for follows directly from the
 * categories chosen for it.
 */
export const CATEGORY_OPERATIONS: Record<ModelCategory, string> = {
  text: 'text.generate',
  conversation: 'text.generate',
  asr: 'audio.transcribe',
  tts: 'audio.synthesize',
  vision: 'vision.analyze',
  video: 'video.labels',
  ocr: 'ocr.extract',
  embedding: 'embedding.generate',
  reranking: 'reranking.rank',
  image_generation: 'image.generate',
  video_generation: 'video.generate',
};

export function operationsForCategories(categories: readonly ModelCategory[]): string[] {
  return [...new Set(categories.map((category) => CATEGORY_OPERATIONS[category]))];
}

export function modelDraft(row: ModelDefinition | null): ModelDraft {
  const categories = row?.categories ?? ['text'];
  return {
    provider: row?.provider ?? 'openai',
    model_key: row?.model_key ?? '',
    display_name: row?.display_name ?? '',
    description: row?.description ?? '',
    publisher: row?.publisher ?? '',
    model_family: row?.model_family ?? '',
    model_version: row?.model_version ?? '',
    categories,
    operations: row?.operations ?? operationsForCategories(categories),
    adapter_status: row?.adapter_status ?? 'unavailable',
    lifecycle: row?.lifecycle === 'retired' ? 'deprecated' : row?.lifecycle ?? 'active',
  };
}

export function validateModelDraft(draft: ModelDraft, creating: boolean): ModelErrors {
  const errors: ModelErrors = {};

  if (!draft.provider.trim()) {
    errors.provider = 'Select a provider.';
  }

  if (creating) {
    if (!draft.model_key.trim()) {
      errors.model_key = 'Enter a model key.';
    } else if (!/^[A-Za-z0-9_.:\/-]{1,160}$/.test(draft.model_key.trim())) {
      errors.model_key = 'Key must be 1 to 160 letters, digits, or characters like _, ., :, / or -.';
    }
  }

  if (!draft.display_name.trim()) {
    errors.display_name = 'Enter a display name.';
  }

  for (const field of Object.keys(MODEL_FIELD_LIMITS) as (keyof typeof MODEL_FIELD_LIMITS)[]) {
    if (draft[field].trim().length > MODEL_FIELD_LIMITS[field]) {
      errors[field] = `Use ${MODEL_FIELD_LIMITS[field]} characters or fewer.`;
    }
  }

  if (draft.categories.length === 0) {
    errors.categories = 'Select at least one category.';
  }

  if (draft.operations.length === 0) {
    errors.operations = 'Select at least one operation.';
  }

  return errors;
}

export function saveModelDraft(
  draft: ModelDraft,
  row: ModelDefinition | null,
  id: string,
  timestamp: string
): ModelDefinition {
  const optional = (value: string) => value.trim() || null;
  return {
    id: row?.id ?? id,
    provider: row?.provider ?? draft.provider.trim(),
    model_key: row?.model_key ?? draft.model_key.trim(),
    display_name: draft.display_name.trim(),
    description: optional(draft.description),
    publisher: optional(draft.publisher),
    model_family: optional(draft.model_family),
    model_version: optional(draft.model_version),
    categories: draft.categories,
    operations: draft.operations,
    capabilities: row?.capabilities ?? {},
    adapter_status: draft.adapter_status,
    lifecycle: draft.lifecycle,
    version: (row?.version ?? 0) + 1,
    created_at: row?.created_at ?? timestamp,
    updated_at: timestamp,
  };
}
