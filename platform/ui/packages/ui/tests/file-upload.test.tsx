/**
 * `FileUpload`.
 *
 * Two things get more attention here than their line count suggests.
 *
 * **Drops, not just the file picker.** `accept` is enforced by the browser on the picker and
 * *not* on a drop — that asymmetry is the whole reason this control validates in JS, so the
 * validation tests go through `drop`, where the browser is guaranteeing nothing.
 *
 * **Every row state.** A file's row is the only place a person learns whether their attachment
 * arrived, so pending, uploading, uploading-without-progress, done and failed are each asserted
 * rather than sampled.
 *
 * Bidi characters are written as `\u202E` escapes rather than pasted in: a literal one in the
 * source reverses the line for whoever reads the file next, which is the very trick under test.
 */
import { createEvent, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { FileUpload, formatBytes, type FileUploadItem } from '../src/components/FileUpload';

/** A real `File` whose `size` is its content length, so size limits can actually be crossed. */
function file(name: string, bytes: number, type = 'application/pdf'): File {
  return new File([new Uint8Array(bytes)], name, { type });
}

function input(name = 'Attachments'): HTMLInputElement {
  return screen.getByLabelText(name) as HTMLInputElement;
}

/** The wrapper that owns the drag handlers — not the `<label>` inside it. */
function dropZone(container: HTMLElement): HTMLElement {
  return container.querySelector('.pms-upload__drop') as HTMLElement;
}

/** jsdom implements no `DataTransfer`, and a drop only needs the two fields the control reads. */
function transfer(files: File[]) {
  return { files, types: files.length > 0 ? ['Files'] : [] };
}

function drop(target: HTMLElement, files: File[]) {
  fireEvent.drop(target, { dataTransfer: transfer(files) });
}

const ITEMS: FileUploadItem[] = [
  { id: 'a', name: 'march-invoice.pdf', size: 240_000, status: 'done', href: '/signed/a' },
  { id: 'b', name: 'gst-return.pdf', size: 1_600_000, status: 'uploading', progress: 42 },
  {
    id: 'c',
    name: 'bank-statement.pdf',
    size: 90_000,
    status: 'failed',
    error: 'Rejected by the server',
  },
  { id: 'd', name: 'notes.pdf', size: 4_096, status: 'pending' },
];

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [512, '512 B'],
    [1024, '1.0 KB'],
    [1536, '1.5 KB'],
    [10 * 1024 * 1024, '10 MB'],
    [1024 ** 4, '1.0 TB'],
  ])('renders %i bytes as %s', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  it('renders nothing for a value that is not a size', () => {
    expect(formatBytes(-1)).toBe('');
    expect(formatBytes(Number.NaN)).toBe('');
  });
});

describe('FileUpload — structure', () => {
  it('takes its accessible name from the field label, not the zone’s own sentence', () => {
    render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    const control = input();
    expect(control.type).toBe('file');
    /* The zone is the input's `<label>` so it can be the click target; the name comes from
     * `aria-labelledby`, which wins — otherwise both would be announced, concatenated. */
    expect(control).toHaveAttribute('aria-labelledby');
  });

  it('keeps the input focusable, and it is the only tab stop for the zone', async () => {
    const user = userEvent.setup();
    render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    /* Clipped, not `display: none`: a hidden-by-display input takes no focus and the control
     * becomes keyboard-unreachable. */
    expect(input()).toHaveClass('pms-visually-hidden');
    await user.tab();
    expect(input()).toHaveFocus();
  });

  it('points the zone’s label at the input', () => {
    const { container } = render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    expect(container.querySelector('label.pms-upload__zone')).toHaveAttribute('for', input().id);
  });

  it('states the limits, and describes the control with them', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        accept=".pdf,image/*"
        acceptLabel="PDF or image"
        maxSizeBytes={5 * 1024 * 1024}
        maxFiles={3}
      />,
    );
    const constraints = screen.getByText('PDF or image · up to 5.0 MB each · 3 files at most');
    expect(input().getAttribute('aria-describedby')?.split(' ')).toContain(constraints.id);
  });

  it('passes accept and multiple through to the native input', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} accept=".pdf" />);
    expect(input()).toHaveAttribute('accept', '.pdf');
    expect(input()).toHaveAttribute('multiple');
  });

  it('is single-file unless asked otherwise', () => {
    render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    expect(input()).not.toHaveAttribute('multiple');
    expect(screen.getByText('Choose a file, or drag it here')).toBeInTheDocument();
  });

  it('invites several files when it takes several', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} />);
    expect(screen.getByText('Choose files, or drag them here')).toBeInTheDocument();
  });

  it('takes the caller’s own sentence for the zone', () => {
    render(<FileUpload label="Attachments" onSelect={vi.fn()} prompt="Drop the signed contract" />);
    expect(screen.getByText('Drop the signed contract')).toBeInTheDocument();
  });

  it('keeps the label as the accessible name when it is hidden from the layout', () => {
    const { container } = render(<FileUpload hideLabel label="Attachments" onSelect={vi.fn()} />);
    expect(input()).toBeInTheDocument();
    // The label itself is clipped; there is no row left to clip.
    expect(screen.getByText('Attachments')).toHaveClass('pms-visually-hidden');
    expect(container.querySelector('.pms-field__row')).toBeNull();
  });

  it('leaves the action visible when the label is hidden', () => {
    render(
      <FileUpload
        hideLabel
        label="Attachments"
        onSelect={vi.fn()}
        action={<a href="/policy">Retention policy</a>}
      />,
    );

    // `pms-visually-hidden` clips rather than removes, so hiding the whole row left this link
    // focusable and invisible — a tab stop a sighted keyboard user cannot see (WCAG 2.4.7).
    expect(screen.getByRole('link', { name: 'Retention policy' }).closest('.pms-visually-hidden')).toBeNull();
    expect(screen.getByText('Attachments')).toHaveClass('pms-visually-hidden');
  });

  it('renders no list until something is attached', () => {
    const { container } = render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    expect(container.querySelector('.pms-upload__list')).toBeNull();
  });

  it('renders the optional note, and lets an action take its place', () => {
    const { rerender } = render(
      <FileUpload label="Attachments" onSelect={vi.fn()} optionalNote="kept for seven years" />,
    );
    expect(screen.getByText('kept for seven years')).toHaveClass('pms-optional');

    rerender(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        optionalNote="kept for seven years"
        action={<a href="/policy">Retention policy</a>}
      />,
    );
    // One slot beside the label, as on `TextField` — the action wins rather than stacking.
    expect(screen.getByRole('link', { name: 'Retention policy' })).toBeInTheDocument();
    expect(screen.queryByText('kept for seven years')).toBeNull();
  });
});

describe('FileUpload — hint, error and requiredness', () => {
  it('renders a hint and points the control at it', () => {
    render(<FileUpload label="Attachments" onSelect={vi.fn()} hint="Scans, not photos." />);
    const hint = screen.getByText('Scans, not photos.');
    expect(input().getAttribute('aria-describedby')?.split(' ')).toContain(hint.id);
    expect(input()).not.toHaveAttribute('aria-invalid');
  });

  it('announces an error, marks the input invalid and flags the field for CSS', () => {
    const { container } = render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        error="At least one document is needed."
      />,
    );
    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent('At least one document is needed.');
    expect(error.querySelector('svg')).not.toBeNull();
    expect(input()).toHaveAttribute('aria-invalid', 'true');
    expect(container.querySelector('.pms-upload')).toHaveAttribute('data-invalid', 'true');
  });

  it('shows the error instead of the hint, and references no paragraph it dropped', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        hint="Scans, not photos."
        error="At least one document is needed."
      />,
    );
    expect(screen.queryByText('Scans, not photos.')).toBeNull();
    // A dangling idref is dropped silently, taking the description that did render with it.
    const described = input().getAttribute('aria-describedby')?.split(' ') ?? [];
    expect(described).toEqual([screen.getByRole('alert').id]);
  });

  it('describes nothing when there is nothing to describe', () => {
    render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    expect(input()).not.toHaveAttribute('aria-describedby');
  });

  /*
   * The input's own value is cleared after every selection, so a `required` left standing would
   * block the submit of a form that does hold files — the control would refuse the very state it
   * asked for.
   */
  it('requires a file only while nothing is attached', () => {
    const { rerender } = render(<FileUpload required label="Attachments" onSelect={vi.fn()} />);
    expect(input()).toBeRequired();

    rerender(<FileUpload required label="Attachments" onSelect={vi.fn()} items={[ITEMS[0]!]} />);
    expect(input()).not.toBeRequired();
  });
});

describe('FileUpload — choosing through the picker', () => {
  it('reports the chosen file and clears the input', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<FileUpload label="Attachments" onSelect={onSelect} />);

    await user.upload(input(), file('march.pdf', 2048));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]![0].map((f: File) => f.name)).toEqual(['march.pdf']);
    /* Cleared so choosing the same file again fires `change` again — otherwise a failed upload
     * cannot be retried by re-picking the file the person already chose. */
    expect(input().value).toBe('');
  });

  it('takes several files when it is a multiple field', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<FileUpload multiple label="Attachments" onSelect={onSelect} />);

    await user.upload(input(), [file('a.pdf', 10), file('b.pdf', 20)]);

    expect(onSelect.mock.calls[0]![0]).toHaveLength(2);
  });
});

describe('FileUpload — dragging and dropping', () => {
  it('offers the dropped files', () => {
    const onSelect = vi.fn();
    const { container } = render(<FileUpload multiple label="Attachments" onSelect={onSelect} />);

    drop(dropZone(container), [file('a.pdf', 10), file('b.pdf', 20)]);

    expect(onSelect.mock.calls[0]![0].map((f: File) => f.name)).toEqual(['a.pdf', 'b.pdf']);
  });

  it('prevents the default on dragover, or the drop never fires at all', () => {
    const { container } = render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    const event = createEvent.dragOver(dropZone(container), {
      dataTransfer: transfer([file('a.pdf', 1)]),
    });

    fireEvent(dropZone(container), event);

    expect(event.defaultPrevented).toBe(true);
  });

  it('lights up while a file drag is over it, and does not flicker on the way in', () => {
    const { container } = render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    const wrap = dropZone(container);
    const inner = container.querySelector('.pms-upload__zone') as HTMLElement;
    const carry = { dataTransfer: transfer([file('a.pdf', 1)]) };

    fireEvent.dragEnter(wrap, carry);
    expect(wrap).toHaveAttribute('data-dragging', 'true');

    /* Moving onto the text inside the zone is a `dragleave` followed by a `dragenter`. Without
     * the depth counter the zone would blink off every time the pointer crossed a child. */
    fireEvent.dragEnter(inner, carry);
    fireEvent.dragLeave(inner, carry);
    expect(wrap).toHaveAttribute('data-dragging', 'true');

    fireEvent.dragLeave(wrap, carry);
    expect(wrap).not.toHaveAttribute('data-dragging');
  });

  it('ignores a drag that carries no files', () => {
    const { container } = render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    // Dragging selected text across the page is not an offer of a file.
    fireEvent.dragEnter(dropZone(container), {
      dataTransfer: { files: [], types: ['text/plain'] },
    });
    expect(dropZone(container)).not.toHaveAttribute('data-dragging');
  });

  it('accepts nothing while disabled', () => {
    const onSelect = vi.fn();
    const { container } = render(<FileUpload disabled label="Attachments" onSelect={onSelect} />);

    fireEvent.dragEnter(dropZone(container), { dataTransfer: transfer([file('a.pdf', 1)]) });
    drop(dropZone(container), [file('a.pdf', 1)]);

    expect(dropZone(container)).not.toHaveAttribute('data-dragging');
    expect(onSelect).not.toHaveBeenCalled();
    expect(input()).toBeDisabled();
    expect(container.querySelector('.pms-upload')).toHaveAttribute('data-disabled', 'true');
  });
});

describe('FileUpload — what it refuses, and why', () => {
  it('refuses a file over the size limit and names both sizes', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload label="Attachments" onSelect={onSelect} maxSizeBytes={1024} />,
    );

    drop(dropZone(container), [file('huge.pdf', 4096)]);

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('huge.pdf is 4.0 KB — the limit is 1.0 KB.');
  });

  it('refuses a type the field does not accept — the browser does not check a drop', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload label="Attachments" onSelect={onSelect} accept=".pdf" acceptLabel="a PDF" />,
    );

    drop(dropZone(container), [file('photo.png', 32, 'image/png')]);

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('photo.png is not a PDF.');
  });

  it('names the raw accept list when it was given no phrase for it', () => {
    const { container } = render(
      <FileUpload label="Attachments" onSelect={vi.fn()} accept=".pdf,.csv" />,
    );

    drop(dropZone(container), [file('photo.png', 32, 'image/png')]);

    expect(screen.getByRole('alert')).toHaveTextContent('photo.png is not one of .pdf,.csv.');
  });

  it('accepts a whole MIME family', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload label="Attachments" onSelect={onSelect} accept="image/*" />,
    );

    drop(dropZone(container), [file('photo.png', 32, 'image/png')]);

    expect(onSelect).toHaveBeenCalled();
  });

  it('accepts an exact MIME type', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload label="Attachments" onSelect={onSelect} accept="application/pdf" />,
    );

    drop(dropZone(container), [file('a.pdf', 32, 'application/pdf')]);

    expect(onSelect).toHaveBeenCalled();
  });

  it('does not let an unknown MIME type satisfy a MIME pattern', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload label="Attachments" onSelect={onSelect} accept="application/pdf" />,
    );

    // `''` matching `application/pdf` would let any extensionless file through on a drop.
    drop(dropZone(container), [file('mystery', 32, '')]);

    expect(onSelect).not.toHaveBeenCalled();
  });

  it('accepts an unknown MIME type on the strength of its extension', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload label="Attachments" onSelect={onSelect} accept=".csv" />,
    );

    // Browsers report `''` for plenty of legitimate files; an extension pattern still holds.
    drop(dropZone(container), [file('ledger.CSV', 32, '')]);

    expect(onSelect).toHaveBeenCalled();
  });

  it('refuses an empty file, which is also what a dropped folder looks like', () => {
    const onSelect = vi.fn();
    const { container } = render(<FileUpload label="Attachments" onSelect={onSelect} />);

    drop(dropZone(container), [file('receipts', 0, '')]);

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('receipts is empty, or is a folder.');
  });

  it('refuses a file already attached', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={onSelect}
        items={[{ id: 'x', name: 'march.pdf', size: 2048, status: 'done' }]}
      />,
    );

    drop(dropZone(container), [file('march.pdf', 2048)]);

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('march.pdf is already attached.');
  });

  it('refuses a re-drop of an attachment whose stored name needed tidying', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={onSelect}
        items={[{ id: 'x', name: ' march\u202Epdf.exe ', size: 2048, status: 'done' }]}
      />,
    );

    // The row shows this name tidied, so the screening set has to be built from the tidied name
    // too. Comparing the raw one let the file the user can plainly see attached in twice.
    drop(dropZone(container), [file(' march\u202Epdf.exe ', 2048)]);

    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('marchpdf.exe is already attached.');
  });

  it('lets a same-named file of a different size through', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={onSelect}
        items={[{ id: 'x', name: 'scan.pdf', size: 2048, status: 'done' }]}
      />,
    );

    // Two devices both name it `scan.pdf`; refusing the second would lose a real document.
    drop(dropZone(container), [file('scan.pdf', 4096)]);

    expect(onSelect).toHaveBeenCalled();
  });

  it('refuses the second copy inside one batch and keeps the first', () => {
    const onSelect = vi.fn();
    const { container } = render(<FileUpload multiple label="Attachments" onSelect={onSelect} />);

    drop(dropZone(container), [file('march.pdf', 2048), file('march.pdf', 2048)]);

    expect(onSelect.mock.calls[0]![0]).toHaveLength(1);
    expect(screen.getByRole('alert')).toHaveTextContent('march.pdf is already attached.');
  });

  it('lists two rejections that share a name and a reason as two rows', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} />);

    // Three copies in one batch: the first is kept and the other two are the same name with the
    // same reason, which is a React key collision if the key is built from those two alone.
    drop(dropZone(container), [
      file('march.pdf', 2048),
      file('march.pdf', 2048),
      file('march.pdf', 2048),
    ]);

    expect(container.querySelectorAll('.pms-upload__rejects li')).toHaveLength(2);
    expect(screen.getByRole('alert')).toHaveTextContent('2 files weren’t added');
    expect(errors).not.toHaveBeenCalled();
    errors.mockRestore();
  });

  it('counts what is already attached against the maximum', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={onSelect}
        maxFiles={2}
        items={[{ id: 'x', name: 'one.pdf', size: 10, status: 'done' }]}
      />,
    );

    drop(dropZone(container), [file('two.pdf', 20), file('three.pdf', 30)]);

    expect(onSelect.mock.calls[0]![0].map((f: File) => f.name)).toEqual(['two.pdf']);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'three.pdf was not added — 2 files is the maximum.',
    );
  });

  it('keeps only the first file on a single-file field', () => {
    const onSelect = vi.fn();
    const { container } = render(<FileUpload label="Attachments" onSelect={onSelect} />);

    drop(dropZone(container), [file('a.pdf', 10), file('b.pdf', 20)]);

    expect(onSelect.mock.calls[0]![0].map((f: File) => f.name)).toEqual(['a.pdf']);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'b.pdf was not added — only one file can be attached.',
    );
  });

  it('hands the rejections to the caller with a machine-readable reason', () => {
    const onReject = vi.fn();
    const { container } = render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        onReject={onReject}
        maxSizeBytes={1024}
      />,
    );

    drop(dropZone(container), [file('huge.pdf', 4096), file('empty.pdf', 0)]);

    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onReject.mock.calls[0]![0].map((r: { reason: string }) => r.reason)).toEqual([
      'size',
      'empty',
    ]);
  });

  it('lists every refusal, and replaces the list on the next batch', () => {
    const { container } = render(
      <FileUpload multiple label="Attachments" onSelect={vi.fn()} maxSizeBytes={1024} />,
    );

    drop(dropZone(container), [file('one.pdf', 4096), file('two.pdf', 4096)]);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('2 files weren’t added');
    expect(within(alert).getAllByRole('listitem')).toHaveLength(2);

    /* A rejection belongs to the batch that produced it — carrying the old ones forward would
     * blame the new drop for the previous one's mistakes. */
    drop(dropZone(container), [file('three.pdf', 4096)]);
    expect(screen.getByRole('alert')).toHaveTextContent('1 file wasn’t added');
    expect(within(screen.getByRole('alert')).getAllByRole('listitem')).toHaveLength(1);
  });

  it('takes the good files from a batch that also had bad ones', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload multiple label="Attachments" onSelect={onSelect} maxSizeBytes={1024} />,
    );

    drop(dropZone(container), [file('fine.pdf', 512), file('huge.pdf', 4096)]);

    expect(onSelect.mock.calls[0]![0].map((f: File) => f.name)).toEqual(['fine.pdf']);
    expect(screen.getByRole('alert')).toHaveTextContent('huge.pdf');
  });

  it('stops offering once the maximum is attached, and says how to carry on', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <FileUpload
        label="Attachments"
        onSelect={onSelect}
        maxFiles={1}
        items={[{ id: 'x', name: 'one.pdf', size: 10, status: 'done' }]}
      />,
    );

    expect(input()).toBeDisabled();
    expect(screen.getByText('One file attached — remove one to add another')).toBeInTheDocument();

    drop(dropZone(container), [file('two.pdf', 20)]);

    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe('FileUpload — the file name is user data', () => {
  /*
   * `invoice` + U+202E + `gnp.exe` renders as `invoiceexe.png`: the override reverses everything
   * after it, so the extension a person reads is not the extension they would run.
   */
  it('strips a bidi override before rendering a name', () => {
    const deceptive = 'invoice\u202Egnp.exe';
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: deceptive, size: 10, status: 'done' }]}
      />,
    );
    expect(screen.getByText('invoicegnp.exe')).toBeInTheDocument();
    expect(screen.queryByText(deceptive)).toBeNull();
  });

  it('names a file that is nothing but control characters', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: '\u202E\u200F', size: 10, status: 'done' }]}
      />,
    );
    expect(screen.getByText('Unnamed file')).toBeInTheDocument();
  });

  it('strips the override from a rejection sentence too', () => {
    const { container } = render(
      <FileUpload label="Attachments" onSelect={vi.fn()} maxSizeBytes={16} />,
    );

    drop(dropZone(container), [file('big\u202Efdp.exe', 64)]);

    expect(screen.getByRole('alert')).toHaveTextContent('bigfdp.exe is 64 B');
  });

  it('names a removed file with the safe name, not the offered one', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        onRemove={vi.fn()}
        items={[{ id: 'x', name: 'a\u202Egnp.exe', size: 10, status: 'done' }]}
      />,
    );
    // The button's accessible name is the name too, so it gets the same treatment.
    expect(screen.getByRole('button', { name: 'Remove agnp.exe' })).toBeInTheDocument();
  });
});

describe('FileUpload — the attachment rows', () => {
  it('renders one row per item, tagged with its status for the CSS', () => {
    const { container } = render(
      <FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />,
    );
    const rows = container.querySelectorAll('.pms-upload__item');
    expect(rows).toHaveLength(4);
    expect([...rows].map((row) => row.getAttribute('data-status'))).toEqual([
      'done',
      'uploading',
      'failed',
      'pending',
    ]);
  });

  it('states the size and the state on every row', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />);
    expect(screen.getByText('234 KB · Uploaded')).toBeInTheDocument();
    expect(screen.getByText('1.5 MB · Uploading… 42%')).toBeInTheDocument();
    expect(screen.getByText('88 KB · Rejected by the server')).toBeInTheDocument();
    expect(screen.getByText('4.0 KB · Waiting')).toBeInTheDocument();
  });

  it('falls back to a plain sentence for a failure the server did not explain', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: 'a.pdf', size: 10, status: 'failed' }]}
      />,
    );
    expect(screen.getByText('10 B · Upload failed')).toBeInTheDocument();
  });

  it('says nothing about a size it was not given', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: 'stored.pdf', status: 'done' }]}
      />,
    );
    expect(screen.getByText('Uploaded')).toBeInTheDocument();
  });

  it('links a finished attachment and nothing else', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />);
    // The point of attaching a document is reading it back; `href` is a signed, expiring URL.
    expect(screen.getByRole('link', { name: 'march-invoice.pdf' })).toHaveAttribute(
      'href',
      '/signed/a',
    );
    expect(screen.queryByRole('link', { name: 'gst-return.pdf' })).toBeNull();
  });

  it('does not link a stored attachment whose upload has not finished', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: 'a.pdf', status: 'uploading', href: '/signed/x' }]}
      />,
    );
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('draws a measured progress bar with the value it was given', () => {
    const { container } = render(
      <FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />,
    );
    const bar = screen.getByRole('progressbar', { name: 'Uploading gst-return.pdf' });
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(bar).not.toHaveAttribute('data-indeterminate');
    expect(container.querySelector<HTMLElement>('.pms-upload__bar-fill')?.style.width).toBe(
      '42%',
    );
  });

  it('clamps a progress value that cannot be true', () => {
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: 'a.pdf', status: 'uploading', progress: 140 }]}
      />,
    );
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });

  /*
   * `aria-valuenow={0}` is a claim that nothing has been sent yet. "In flight, no measurement" is
   * a different fact, and an indeterminate progressbar is how it is spelled.
   */
  it('claims no value when there is no measurement', () => {
    const { container } = render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        items={[{ id: 'x', name: 'a.pdf', size: 10, status: 'uploading' }]}
      />,
    );
    const bar = screen.getByRole('progressbar');
    expect(bar).not.toHaveAttribute('aria-valuenow');
    expect(bar).toHaveAttribute('data-indeterminate', 'true');
    expect(screen.getByText('10 B · Uploading…')).toBeInTheDocument();
    expect(container.querySelector<HTMLElement>('.pms-upload__bar-fill')?.style.width).toBe('');
  });

  it('shows a progress bar only while a row is uploading', () => {
    render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        items={ITEMS.filter((item) => item.status !== 'uploading')}
      />,
    );
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
});

describe('FileUpload — row actions', () => {
  it('offers retry on a failed row only, and hands back the item', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        items={ITEMS}
        onRetry={onRetry}
      />,
    );

    const retries = screen.getAllByRole('button', { name: 'Retry' });
    expect(retries).toHaveLength(1);

    await user.click(retries[0]!);
    expect(onRetry).toHaveBeenCalledWith(ITEMS[2]);
  });

  it('offers no retry when the caller has no way to retry', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />);
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });

  it('names each remove button after its own file', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        items={ITEMS}
        onRemove={onRemove}
      />,
    );

    // Four buttons all called "Remove" is a list a screen-reader user cannot navigate.
    expect(screen.getAllByRole('button', { name: /^Remove / })).toHaveLength(4);
    await user.click(screen.getByRole('button', { name: 'Remove notes.pdf' }));
    expect(onRemove).toHaveBeenCalledWith(ITEMS[3]);
  });

  it('offers no remove button when the caller has no way to remove', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />);
    expect(screen.queryByRole('button', { name: /^Remove / })).toBeNull();
  });

  it('disables removal while the field is disabled', () => {
    render(
      <FileUpload
        disabled
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        items={ITEMS}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Remove notes.pdf' })).toBeDisabled();
  });

  it('keeps removal available when only the maximum has been reached', () => {
    // `atLimit` closes the zone, not the list — otherwise the way out of the limit is blocked.
    render(
      <FileUpload
        label="Attachments"
        onSelect={vi.fn()}
        maxFiles={1}
        items={[ITEMS[0]!]}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Remove march-invoice.pdf' })).toBeEnabled();
  });
});

describe('FileUpload — announcements', () => {
  it('announces progress once per batch rather than per tick', () => {
    render(<FileUpload multiple label="Attachments" onSelect={vi.fn()} items={ITEMS} />);
    /* One sentence for the whole list: a region that re-read every percentage would talk over
     * everything else on the page. */
    expect(screen.getByRole('status')).toHaveTextContent('Uploading 1 of 4');
  });

  it('announces a failure once nothing is in flight', () => {
    render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        items={ITEMS.filter((item) => item.status !== 'uploading')}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('1 upload failed');
  });

  it('announces success when everything landed', () => {
    render(
      <FileUpload
        multiple
        label="Attachments"
        onSelect={vi.fn()}
        items={ITEMS.filter((item) => item.status === 'done')}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('1 file uploaded');
  });

  it('says nothing when there is nothing to say', () => {
    render(<FileUpload label="Attachments" onSelect={vi.fn()} />);
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });
});
