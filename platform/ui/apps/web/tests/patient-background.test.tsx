import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { expect, it, vi } from 'vitest';
import { CaseFields } from '../src/components/CaseFields';
import { emptyDocument } from '../src/lib/patient-catalog';

function Editor() {
  const [document, setDocument] = useState(emptyDocument());
  return <><CaseFields document={document} onChange={setDocument} section="background" language="en" />
    <output data-testid="saved">{JSON.stringify(document)}</output></>;
}

it('upgrades a legacy draft when background is added and keeps variation explicit', () => {
  render(<Editor />);
  fireEvent.click(within(screen.getByRole('region', { name: 'Food & drink' })).getByText('Approved everyday details'));
  const allow = screen.getByRole('checkbox', { name: 'Allow approved everyday details for food & drink' });
  expect(allow).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Food & drink background (en)'), { target: { value: 'Home-cooked meals.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add food & drink detail' }));
  fireEvent.change(screen.getByLabelText('Food & drink everyday detail 1 (en)'), { target: { value: 'Rice and vegetables.' } });
  expect(allow).not.toBeChecked();
  fireEvent.click(allow);
  const saved = JSON.parse(screen.getByTestId('saved').textContent!);
  expect(saved.version).toBe(5);
  expect(saved.background[0]).toMatchObject({ text: { en: 'Home-cooked meals.' }, allow_variation: true,
    choices: [{ id: 'choice_1', text: { en: 'Rice and vegetables.' } }] });
  fireEvent.click(screen.getByRole('button', { name: 'Remove food & drink detail 1' }));
  expect(allow).not.toBeChecked();
  expect(allow).toBeDisabled();
});

it('keeps the three-detail limit and disables variation when the final detail is removed', () => {
  render(<Editor />);
  const food = within(screen.getByRole('region', { name: 'Food & drink' }));
  fireEvent.click(food.getByText('Approved everyday details'));
  const add = food.getByRole('button', { name: 'Add food & drink detail' });
  expect(add).toBeDisabled();
  fireEvent.change(food.getByLabelText('Food & drink background (en)'), { target: { value: 'Home meals.' } });
  for (let index = 1; index <= 3; index++) {
    fireEvent.click(add);
    fireEvent.change(food.getByLabelText('Food & drink everyday detail ' + index + ' (en)'), { target: { value: 'Detail ' + index } });
  }
  expect(add).toBeDisabled();
  expect(JSON.parse(screen.getByTestId('saved').textContent!).background[0].choices).toHaveLength(3);
  fireEvent.click(food.getByRole('checkbox'));
  for (let index = 3; index >= 1; index--) fireEvent.click(food.getByRole('button', { name: 'Remove food & drink detail ' + index }));
  expect(food.getByRole('checkbox')).toBeDisabled();
  expect(food.getByRole('checkbox')).not.toBeChecked();
  expect(add).toBeEnabled();
});

it('shows saved background and approved details as readable content without edit controls', () => {
  const onChange = vi.fn();
  const document = { ...emptyDocument(), version: 5 as const, background: [{ id: 'food_drink' as const,
    text: { en: 'Home meals.', hi: 'भोजन।' }, allow_variation: false,
    choices: [{ id: 'choice_1', text: { en: 'Rice and vegetables.' } }] }] };
  render(<CaseFields document={document} onChange={onChange} section="background" language="en" readOnly />);
  expect(screen.getByText('Home meals.')).toBeInTheDocument();
  expect(screen.getByText('Rice and vegetables.')).toBeInTheDocument();
  expect(screen.getByText('Not enabled for conversation')).toBeInTheDocument();
  expect(screen.getAllByText('Not specified')).toHaveLength(4);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

it('keeps missing translations explicit in the reading view', () => {
  const document = { ...emptyDocument(), version: 5 as const, background: [{ id: 'food_drink' as const,
    text: { en: 'Home meals.' }, allow_variation: true,
    choices: [{ id: 'choice_1', text: { en: 'Rice and vegetables.' } }] }] };
  render(<CaseFields document={document} onChange={vi.fn()} section="background" language="hi" readOnly />);
  expect(screen.getAllByText('Translation missing')).toHaveLength(2);
  expect(screen.getByText('Enabled for conversation')).toBeInTheDocument();
  expect(screen.queryByText('Home meals.')).not.toBeInTheDocument();
});

it('preserves other languages while editing the selected background translation', () => {
  let updated: unknown;
  const document = { ...emptyDocument(), version: 5 as const, background: [{ id: 'food_drink' as const,
    text: { en: 'Meals.', hi: 'भोजन।' }, allow_variation: false, choices: [] }] };
  render(<CaseFields document={document} onChange={(value) => { updated = value; }} section="background" language="en" />);
  fireEvent.change(screen.getByLabelText('Food & drink background (en)'), { target: { value: 'Home food.' } });
  expect(updated).toMatchObject({ background: [{ text: { en: 'Home food.', hi: 'भोजन।' } }] });
});
