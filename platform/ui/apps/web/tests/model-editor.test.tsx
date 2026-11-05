import { StrictMode } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ModelEditor } from '../src/components/ModelEditor';
import { DEMO_MODELS } from '../src/data/models';
import { saveModelDraft, modelDraft, operationsForCategories, validateModelDraft } from '../src/lib/model-editor';

const model = DEMO_MODELS[0]!;
const providers = [{ id: 'openai', operations: ['text.generate'], adapterAvailable: true }];
const valid = () => ({
  ...modelDraft(null),
  model_key: 'claude-3-opus',
  display_name: 'Claude 3 Opus (Cloud)',
  categories: ['text' as const],
});

describe('model editor data', () => {
  it('requires a valid model key and display name on creation', () => {
    expect(validateModelDraft({ ...valid(), model_key: '   ' }, true))
      .toEqual({ model_key: 'Enter a model key.' });
    expect(validateModelDraft({ ...valid(), model_key: 'invalid key!' }, true))
      .toHaveProperty('model_key');
    expect(validateModelDraft({ ...valid(), display_name: '' }, true))
      .toEqual({ display_name: 'Enter a display name.' });
  });

  it.each([['model_key', 160], ['display_name', 256], ['description', 4000]] as const)(
    'honors the API length boundary for %s', (field, max) => {
      expect(validateModelDraft({ ...valid(), [field]: 'x'.repeat(max) }, true)[field]).toBeUndefined();
      expect(validateModelDraft({ ...valid(), [field]: 'x'.repeat(max + 1) }, true)[field]).toBeDefined();
    },
  );

  it('derives operations from the selected categories, deduplicated', () => {
    expect(operationsForCategories(['text', 'conversation'])).toEqual(['text.generate']);
    expect(operationsForCategories(['asr', 'tts'])).toEqual(['audio.transcribe', 'audio.synthesize']);
    expect(operationsForCategories([])).toEqual([]);
  });

  it('creates records, trims fields and keeps management values consistent', () => {
    const saved = saveModelDraft({
      ...valid(),
      model_key: '  claude-3-opus  ',
      display_name: '  Claude 3 Opus  ',
      description: '  Anthropic flagship.  ',
    }, null, 'new-id', 'timestamp');

    expect(saved).toMatchObject({
      id: 'new-id',
      model_key: 'claude-3-opus',
      display_name: 'Claude 3 Opus',
      description: 'Anthropic flagship.',
      created_at: 'timestamp',
      updated_at: 'timestamp',
      version: 1,
    });
  });

  it('preserves keys and identity when editing', () => {
    const draft = { ...modelDraft(model), display_name: 'Renamed Model' };
    expect(validateModelDraft(draft, false)).toEqual({});
    expect(saveModelDraft(draft, model, 'ignored', 'later')).toMatchObject({
      id: model.id,
      display_name: 'Renamed Model',
      model_key: model.model_key,
      created_at: model.created_at,
      updated_at: 'later',
      version: model.version + 1,
    });
  });
});

describe('model editor controls', () => {
  it('does not show errors while an untouched form mounts', async () => {
    const user = userEvent.setup();
    render(<StrictMode><ModelEditor model={null} providers={providers} onSave={vi.fn()} onClose={() => {}} /></StrictMode>);
    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveFocus();
    await user.tab();
    expect(screen.queryByText('Enter a model key.')).not.toBeInTheDocument();
  });

  it('registers a model once the required fields and a category are provided', async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    render(<ModelEditor model={null} providers={providers} onSave={save} onClose={() => {}} />);

    const registerBtn = screen.getByRole('button', { name: 'Register model' });
    await user.click(registerBtn);
    expect(screen.getByText('Enter a display name.')).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();

    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Test Claude');
    await user.type(screen.getByRole('textbox', { name: 'Model key' }), 'claude-test');
    // 'Text Processing' is selected by default (a new draft always starts with the 'text' category).
    expect(screen.getByRole('button', { name: 'Text Processing' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(registerBtn);
    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      display_name: 'Test Claude', model_key: 'claude-test', categories: ['text'], operations: ['text.generate'],
    }));
  });

  it('protects a dirty draft on Escape and asks for confirmation', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<ModelEditor model={null} providers={providers} onSave={vi.fn()} onClose={close} />);

    await user.type(screen.getByRole('textbox', { name: 'Display name' }), 'Draft Model Name');
    await user.keyboard('{Escape}');

    const confirmation = screen.getByRole('dialog', { name: 'Discard unsaved changes?' });
    expect(within(confirmation).getByRole('button', { name: 'Keep editing' })).toHaveFocus();

    await user.click(within(confirmation).getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveValue('Draft Model Name');

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it('does not warn or save an unchanged edit, and allows Cancel immediately', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    const save = vi.fn();
    render(<ModelEditor model={model} providers={providers} onSave={save} onClose={close} />);

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(close).toHaveBeenCalledOnce();
    expect(save).not.toHaveBeenCalled();
  });

  it('keeps provider and model key read only when editing', () => {
    render(<ModelEditor model={model} providers={providers} onSave={vi.fn()} onClose={() => {}} />);
    expect(screen.getByRole('textbox', { name: 'Provider' })).toHaveAttribute('readonly');
    expect(screen.getByRole('textbox', { name: 'Model key' })).toHaveAttribute('readonly');
  });
});
