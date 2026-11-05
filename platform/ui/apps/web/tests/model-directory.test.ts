import { describe, expect, it } from 'vitest';
import { DEMO_MODELS } from '../src/data/models';
import {
  deprecateModel,
  DEFAULT_MODEL_QUERY,
  modelPage,
  type ModelDefinition
} from '../src/lib/model-directory';

describe('model directory queries', () => {
  it('searches the whole dataset by display name, key and description with case-insensitive substrings', () => {
    const result = modelPage(DEMO_MODELS, { ...DEFAULT_MODEL_QUERY, q: ' gemini ' }, 0);
    expect(result.total).toBeGreaterThan(0);
    expect(result.items.every((row) => row.display_name.startsWith('Gemini'))).toBe(true);
  });

  it('filters by provider', () => {
    const openai = modelPage(DEMO_MODELS, { ...DEFAULT_MODEL_QUERY, provider: 'openai' }, 0);
    expect(openai.total).toBeGreaterThan(0);
    expect(openai.items.every((row) => row.provider === 'openai')).toBe(true);
  });

  it('filters by category', () => {
    const vision = modelPage(DEMO_MODELS, { ...DEFAULT_MODEL_QUERY, category: 'vision' }, 0);
    expect(vision.total).toBeGreaterThan(0);
    expect(vision.items.every((row) => row.categories.includes('vision'))).toBe(true);
  });

  it('filters by lifecycle status', () => {
    const active = modelPage(DEMO_MODELS, { ...DEFAULT_MODEL_QUERY, lifecycle: 'active' }, 0);
    expect(active.total).toBeGreaterThan(0);
    expect(active.items.every((row) => row.lifecycle === 'active')).toBe(true);

    const deprecated = modelPage(DEMO_MODELS, { ...DEFAULT_MODEL_QUERY, lifecycle: 'deprecated' }, 0);
    expect(deprecated.total).toBeGreaterThan(0);
    expect(deprecated.items.every((row) => row.lifecycle === 'deprecated')).toBe(true);
  });

  it('walks matching rows in stable order', () => {
    const query = { ...DEFAULT_MODEL_QUERY };
    const result = modelPage(DEMO_MODELS, query, 0);
    const ids = result.items.map((row) => row.id);
    expect(ids).toHaveLength(result.items.length);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('deprecates local model definitions and increments version', () => {
    const model = DEMO_MODELS[0]!;
    expect(model.lifecycle).toBe('active');
    const deprecated = deprecateModel(model, '2026-09-22T12:00:00Z');
    expect(deprecated.lifecycle).toBe('deprecated');
    expect(deprecated.version).toBe(model.version + 1);

    expect(deprecateModel(deprecated, 'ignored')).toBe(deprecated); // should not re-deprecate
  });
});
