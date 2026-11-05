import type { ReactNode } from 'react';
/** Read-only existing documents; React escapes text and no HTML/JSON editor is exposed. */
export function StructuredRecord({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  if (value === null || value === undefined) return <span className="pms-meta">Not set</span>;
  if (typeof value !== 'object') return <span>{String(value)}</span>;
  if (depth >= 8) return <span className="pms-meta">Additional detail</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ol>
        {value.slice(0, 100).map((v, i) => (
          <li key={i}>
            <StructuredRecord value={v} depth={depth + 1} />
          </li>
        ))}
      </ol>
    ) : (
      <span className="pms-meta">None</span>
    );
  return (
    <dl>
      {Object.entries(value)
        .filter(([key]) => key !== 'localizations')
        .map(([key, v]) => (
          <div key={key}>
            <dt>
              <strong>{key.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())}</strong>
            </dt>
            <dd>
              <StructuredRecord value={v} depth={depth + 1} />
            </dd>
          </div>
        ))}
    </dl>
  );
}
