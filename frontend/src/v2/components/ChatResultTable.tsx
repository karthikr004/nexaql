import { useState } from 'react';
import type { ColumnMeta } from '../../types';

interface Props {
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  rowCount: number;
}

export default function ChatResultTable({ rows, columns, rowCount }: Props) {
  const [expanded, setExpanded] = useState(false);
  const display = expanded ? rows : rows.slice(0, 5);
  const hasMore = rows.length > 5;

  if (!rows.length) return null;

  const cleanName = (n: string) => n.replace(/__/g, '.');
  const formatValue = (v: unknown) => {
    const s = String(v);
    if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(s)) return s.slice(0, 10);
    return s;
  };

  return (
    <div className="v2-card" style={{ overflow: 'hidden' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 14px',
          borderBottom: '1px solid var(--v2-border)',
          background: 'var(--v2-bg-surface)',
        }}
      >
        <span className="v2-label" style={{ fontSize: 10 }}>Results</span>
        <span className="v2-badge v2-badge-teal" style={{ fontSize: 10 }}>
          {rowCount} row{rowCount !== 1 ? 's' : ''}
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="v2-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.name}
                  style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, whiteSpace: 'nowrap' }}
                >
                  {cleanName(c.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {display.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => {
                  const v = row[c.name];
                  return (
                    <td
                      key={c.name}
                      style={{
                        fontFamily: 'var(--v2-font-mono)',
                        fontSize: 12,
                        whiteSpace: 'nowrap',
                        maxWidth: 240,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {v === null || v === undefined ? (
                        <span style={{ color: 'var(--v2-text-tertiary)', fontStyle: 'italic' }}>null</span>
                      ) : (
                        formatValue(v)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          style={{
            width: '100%',
            padding: '6px 14px',
            borderTop: '1px solid var(--v2-border)',
            background: 'var(--v2-bg-surface)',
            color: 'var(--v2-text-tertiary)',
            fontSize: 11,
            fontFamily: 'var(--v2-font-sans)',
            cursor: 'pointer',
            border: 'none',
            borderTopStyle: 'solid',
            borderTopWidth: 1,
            borderTopColor: 'var(--v2-border)',
            transition: 'color var(--v2-transition-fast)',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--v2-text-primary)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--v2-text-tertiary)'; }}
        >
          {expanded ? 'Show less' : `Show all ${rowCount} rows`}
        </button>
      )}
    </div>
  );
}
