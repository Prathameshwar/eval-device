import { ThemeProvider, currentYear } from '@pms/ui';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AuthLayout from '../src/app/(auth)/layout';

/**
 * The layout is a server component, but it is also just a function returning markup — no `async`,
 * no request access — so it renders here directly. `ThemeProvider` is supplied because the root
 * layout normally provides it and `ThemeSwitcher` requires it.
 */
function renderLayout() {
  return render(
    <ThemeProvider>
      <AuthLayout>
        <p>form goes here</p>
      </AuthLayout>
    </ThemeProvider>,
  );
}

describe('auth layout', () => {
  it('shows the identity, the claim and the argument beside the form', () => {
    const { container } = renderLayout();

    expect(container).toHaveTextContent('AI Evaluator');
    expect(screen.getByText(/Clinical conversations, scored with evidence/)).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByText('Traceable to the transcript')).toBeInTheDocument();
    expect(screen.getByText('form goes here')).toBeInTheDocument();
  });

  it('offers the theme control and a current copyright line', () => {
    renderLayout();

    expect(screen.getByRole('radiogroup', { name: 'Colour theme' })).toBeInTheDocument();
    expect(screen.getByText(`© ${currentYear()} AI Evaluator`)).toBeInTheDocument();
  });

  it('labels account access without false preview or certification claims', () => {
    const { container } = renderLayout();

    expect(screen.getByText('Account access')).toBeInTheDocument();
    expect(screen.queryByText(/sign-in not connected/i)).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/SOC ?2|HIPAA|ISO ?27001|certified/i);
  });
});
