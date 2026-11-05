'use client';
import { createContext, useContext, useRef, useState, type ReactNode } from 'react';
import { DEFAULT_MODEL_QUERY, type ModelDefinition } from '@/lib/model-directory';
import { validateModelDraft, type ModelDraft } from '@/lib/model-editor';
import { listModels, saveModel, retireModel, restoreModel, type ProviderOption } from '@/lib/model-actions';
import { useApiDirectory } from '@/lib/use-api-directory';

type SavedModel = { id: string; name: string; created: boolean };
type SaveResult = { model: ModelDefinition; error?: never } | { model?: never; error: string };

function useDirectoryState(initialRows: readonly ModelDefinition[], providers: readonly ProviderOption[]) {
  const [rows, setRows] = useState(initialRows);
  const directory = useApiDirectory(DEFAULT_MODEL_QUERY, listModels);
  const [savedModel, setSavedModel] = useState<SavedModel | null>(null);
  const listBookmark = useRef<{ id: string; tableTop: number; pageTop: number } | null>(null);
  function remember(row: ModelDefinition) {
    setRows((current) => [row, ...current.filter((item) => item.id !== row.id)]);
    directory.reload();
  }
  async function save(draft: ModelDraft, original: ModelDefinition | null): Promise<SaveResult> {
    if (Object.keys(validateModelDraft(draft, !original)).length) return { error: 'Check the model details before saving.' };
    const result = await saveModel(draft, original?.id, original?.version);
    if (result.error !== undefined) return { error: result.error };
    remember(result.value);
    setSavedModel({ id: result.value.id, name: result.value.display_name, created: !original });
    return { model: result.value };
  }
  async function retire(original: ModelDefinition): Promise<string | undefined> {
    try {
      const result = await retireModel(original.id);
      if (result.error !== undefined) return result.error;
      remember(result.value);
      setSavedModel(null);
    } catch { return 'Unable to complete this request. Refresh to check the model before retrying.'; }
  }
  async function restore(original: ModelDefinition): Promise<string | undefined> {
    try {
      const result = await restoreModel(original.id, original.version);
      if (result.error !== undefined) return result.error;
      remember(result.value);
      setSavedModel(null);
    } catch { return 'Unable to complete this request. Refresh to check the model before retrying.'; }
  }
  return { ...directory, rows, providers, savedModel, setSavedModel, listBookmark, save, retire, restore, remember };
}

const DirectoryContext = createContext<ReturnType<typeof useDirectoryState> | null>(null);

export function ModelDirectoryProvider({ initialRows = [], providers = [], children }: {
  initialRows?: readonly ModelDefinition[];
  providers?: readonly ProviderOption[];
  children: ReactNode;
}) {
  const state = useDirectoryState(initialRows, providers);
  return <DirectoryContext.Provider value={state}>{children}</DirectoryContext.Provider>;
}

export function useModelDirectory() {
  const state = useContext(DirectoryContext);
  if (!state) throw new Error('Model pages require ModelDirectoryProvider.');
  return state;
}
