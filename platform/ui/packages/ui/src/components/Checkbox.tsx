import type { InputHTMLAttributes, ReactNode } from 'react';
import { CheckIcon } from './icons';

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  children: ReactNode;
  /**
   * The third state: *some* of what this box stands for is selected — a page where four of fifty
   * rows are ticked.
   *
   * It lives here rather than at the call site because HTML has no `indeterminate` attribute: it is
   * a DOM property only, so it has to be set through a ref, and every select-all box in the
   * application would otherwise carry its own copy of that. Browsers expose the property as
   * `aria-checked="mixed"` on their own, so nothing is stated twice.
   */
  indeterminate?: boolean;
};

export function Checkbox({ children, indeterminate = false, ...input }: CheckboxProps) {
  return (
    <label className="pms-check">
      <input
        type="checkbox"
        // A fresh callback each render, deliberately: React re-runs it, which is what keeps the
        // property in step with the prop after the parent re-renders with a different selection.
        ref={(element) => {
          if (element) element.indeterminate = indeterminate;
        }}
        {...input}
      />
      <span className="pms-check__box" aria-hidden="true">
        <CheckIcon size={12} />
      </span>
      <span>{children}</span>
    </label>
  );
}
