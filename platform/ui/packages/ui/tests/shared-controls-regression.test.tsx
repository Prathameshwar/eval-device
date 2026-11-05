import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode, useState } from 'react';
import { SearchSelect } from '../src/components/SearchSelect';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppFooter } from '../src/components/AppFooter';
import { Button } from '../src/components/Button';
import { ConfirmDialog } from '../src/components/ConfirmDialog';
import { Menu } from '../src/components/Menu';
import { Modal } from '../src/components/Overlay';
import { RailItem } from '../src/components/Rail';
import { Select } from '../src/components/Select';
import { Tabs, tabButtonId } from '../src/components/Tabs';
import { TextField } from '../src/components/TextField';
import { isSafeHref } from '../src/lib/url';

afterEach(() => {
  cleanup();
  document.body.style.overflow = '';
});

describe('shared controls in forms', () => {
  it('requires an explicit submit type and retains native reset behavior', async () => {
    const user = userEvent.setup();
    const submit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={submit}>
        <TextField label="Name" defaultValue="Before" />
        <Button>Cancel</Button>
        <Button type="submit">Save</Button>
        <Button type="reset">Reset</Button>
      </form>,
    );
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(submit).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Name'), ' changed');
    await user.click(screen.getByRole('button', { name: 'Reset' }));
    expect(screen.getByLabelText('Name')).toHaveValue('Before');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('does not reference a hint hidden by an error', () => {
    render(<TextField label="Name" hint="Hint" error="Required" />);
    const ids = screen.getByLabelText('Name').getAttribute('aria-describedby')!.split(' ');
    expect(ids).toHaveLength(1);
    expect(document.getElementById(ids[0]!)).toHaveTextContent('Required');
  });

  it('keeps external descriptions together with field error semantics', () => {
    render(<>
      <p id="guidance">External guidance</p>
      <TextField label="Name" hint="Hint" error="Required"
        aria-describedby="guidance" aria-invalid={false} />
    </>);
    expect(screen.getByLabelText('Name')).toHaveAccessibleDescription(/External guidance/);
    expect(screen.getByLabelText('Name')).toHaveAccessibleDescription(/Required/);
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true');
  });

  it('preserves caller validation when no component error is supplied', () => {
    render(<TextField label="Name" aria-invalid="grammar" />);
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'grammar');
  });

  it('merges external, loading and validation descriptions on selects', () => {
    render(<>
      <p id="guidance">External guidance</p>
      <Select label="Choice" name="choice" value="a" onChange={vi.fn()}
        options={[{ value: 'a', label: 'A' }]} loading error="Choose again"
        aria-describedby="guidance" aria-invalid={false} aria-busy={false} />
    </>);
    const control = screen.getByLabelText('Choice');
    expect(control).toHaveAccessibleDescription(/External guidance/);
    expect(control).toHaveAccessibleDescription(/Loading/);
    expect(control).toHaveAccessibleDescription(/Choose again/);
    expect(control).toHaveAttribute('aria-invalid', 'true');
    expect(control).toHaveAttribute('aria-busy', 'true');
  });

  it.each([true, false])('honors an external form while loading=%s', (loading) => {
    render(<>
      <form id="preferences" aria-label="Preferences" />
      <Select label="Choice" name="choice" form="preferences" value="a" onChange={vi.fn()}
        options={[{ value: 'a', label: 'A' }]} loading={loading} />
    </>);
    const form = screen.getByRole('form') as HTMLFormElement;
    expect(new FormData(form).getAll('choice')).toEqual(['a']);
  });

  it('does not submit an explicitly disabled loading select', () => {
    render(<>
      <form id="preferences" aria-label="Preferences" />
      <Select label="Choice" name="choice" form="preferences" value="a" onChange={vi.fn()}
        options={[]} loading disabled />
    </>);
    expect(new FormData(screen.getByRole('form') as HTMLFormElement).has('choice')).toBe(false);
  });
});

describe('shared dialog composition', () => {
  it('focuses and traps the panel when no controls are available', async () => {
    const user = userEvent.setup();
    render(<>
      <button>Background</button>
      <Modal open title="Read only" dismissible={false} onClose={vi.fn()}>Details</Modal>
    </>);
    const panel = screen.getByRole('dialog');
    expect(panel).toHaveFocus();
    await user.tab();
    expect(panel).toHaveFocus();
    await user.tab({ shift: true });
    expect(panel).toHaveFocus();
  });

  it('focuses the panel when all confirmation actions are busy', () => {
    render(<ConfirmDialog open busy title="Processing" onConfirm={vi.fn()} onCancel={vi.fn()}>
      Please wait
    </ConfirmDialog>);
    expect(screen.getByRole('dialog')).toHaveFocus();
  });

  it('excludes hidden, inert, negative-tabindex and disabled-fieldset controls', async () => {
    const user = userEvent.setup();
    render(<Modal open title="Edit" dismissible={false} onClose={vi.fn()}>
      <input type="hidden" value="hidden" readOnly />
      <button tabIndex={-1}>Programmatic only</button>
      <div hidden><button>Hidden ancestor</button></div>
      <div style={{ display: 'none' }}><button>CSS hidden</button></div>
      <div inert><button>Inert</button></div>
      <fieldset disabled><button>Disabled fieldset</button></fieldset>
      <button>First</button><button>Last</button>
      <button style={{ visibility: 'hidden' }}>Invisible</button>
    </Modal>);
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Last' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus();
  });

  it('lets a child menu consume Escape before the containing dialog', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<Modal open title="Edit" onClose={close}>
      <Menu label="Actions" items={[{ id: 'edit', label: 'Edit item' }]} onSelect={vi.fn()} />
    </Modal>);
    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(close).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(close).toHaveBeenCalledTimes(1);
  });

  it('only dismisses the nested dialog on Escape and returns focus to its opener', async () => {
    const user = userEvent.setup();
    const outerClose = vi.fn();
    function Host() {
      const [inner, setInner] = useState(false);
      return <Modal open title="Outer" onClose={outerClose}>
        <button onClick={() => setInner(true)}>Open inner</button>
        <Modal open={inner} title="Inner" onClose={() => setInner(false)}>Details</Modal>
      </Modal>;
    }
    render(<Host />);
    const opener = screen.getByRole('button', { name: 'Open inner' });
    await user.click(opener);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Inner' })).not.toBeInTheDocument();
    expect(outerClose).not.toHaveBeenCalled();
    expect(opener).toHaveFocus();
  });

  it('retains scroll locking and focus when overlapping dialogs close out of order', () => {
    document.body.style.overflow = 'auto';
    function Host({ first, second }: { first: boolean; second: boolean }) {
      return <>
        <Modal open={first} title="First" onClose={vi.fn()}>First</Modal>
        <Modal open={second} title="Second" onClose={vi.fn()}>Second</Modal>
      </>;
    }
    const { rerender } = render(<Host first second={false} />);
    rerender(<Host first second />);
    const secondClose = within(screen.getByRole('dialog', { name: 'Second' })).getByRole('button');
    expect(secondClose).toHaveFocus();
    rerender(<Host first={false} second />);
    expect(document.body.style.overflow).toBe('hidden');
    expect(secondClose).toHaveFocus();
    rerender(<Host first={false} second={false} />);
    expect(document.body.style.overflow).toBe('auto');
  });
});

describe('shared navigation links', () => {
  it('rejects a backslash host disguised as a local path', () => {
    const disguised = '/\\external.example/path';
    expect(new URL(disguised, 'https://app.example').origin).toBe('https://external.example');
    expect(isSafeHref(disguised)).toBe(false);
  });

  it.each(['javascript:alert(1)', 'data:text/html,bad', '//external.example', '/\\external.example'])(
    'renders unsafe footer and rail destinations as plain text: %s', (href) => {
      render(<>
        <AppFooter links={[{ label: 'Help', href }]} copyright="Example" />
        <ul><RailItem icon={<span />} label="Settings" href={href} /></ul>
      </>);
      expect(screen.queryAllByRole('link')).toHaveLength(0);
      expect(screen.getByText('Help')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    },
  );
});

describe('dialog integration follow-up', () => {
  it('lets Escape reach the dialog after the search list is closed and its query is empty', async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<Modal open title="Choose" onClose={close}>
      <SearchSelect label="Item" options={[{ id: 'one', label: 'One' }]}
        value={null} onChange={vi.fn()} />
    </Modal>);
    await user.click(screen.getByRole('combobox'));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(close).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(close).toHaveBeenCalledTimes(1);
  });

  it('restores the original opener through an out-of-order close under StrictMode', () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    document.body.style.setProperty('overflow', 'scroll', 'important');
    function Host({ first, second }: { first: boolean; second: boolean }) {
      return <StrictMode>
        <Modal open={first} title="First" onClose={vi.fn()}>First</Modal>
        <Modal open={second} title="Second" onClose={vi.fn()}>Second</Modal>
      </StrictMode>;
    }
    try {
      const { rerender, unmount } = render(<Host first second={false} />);
      rerender(<Host first second />);
      rerender(<Host first={false} second />);
      rerender(<Host first={false} second={false} />);
      expect(opener).toHaveFocus();
      expect(document.body.style.overflow).toBe('scroll');
      expect(document.body.style.getPropertyPriority('overflow')).toBe('important');
      unmount();
    } finally {
      opener.remove();
    }
  });
});

describe('independent tab groups', () => {
  const tabs = [{ id: 'overview', label: 'Overview' }, { id: 'details', label: 'Details' }];

  it('gives repeated tab ids unique DOM ids with or without panels', () => {
    render(<>
      <Tabs tabs={tabs} active="overview" label="First" onChange={vi.fn()} panelId="first-panel" />
      <Tabs tabs={tabs} active="overview" label="Second" onChange={vi.fn()} panelId="second-panel" />
      <Tabs tabs={tabs} active="overview" label="Third" onChange={vi.fn()} />
      <Tabs tabs={tabs} active="overview" label="Fourth" onChange={vi.fn()} />
    </>);
    const ids = screen.getAllByRole('tab').map((tab) => tab.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(within(screen.getByRole('tablist', { name: 'First' })).getByRole('tab', { name: 'Overview' }))
      .toHaveAttribute('id', tabButtonId('overview', 'first-panel'));
  });

  it('does not collide when panel and tab ids contain delimiters', () => {
    expect(tabButtonId('c', 'a--b')).not.toBe(tabButtonId('b--c', 'a'));
  });

  it('keeps a tab stop when the selected tab has been removed', async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    render(<Tabs tabs={tabs} active="removed" label="Sections" onChange={change} />);
    await user.tab();
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveFocus();
    await user.keyboard('{ArrowRight}');
    expect(change).toHaveBeenCalledWith('details');
  });
});
