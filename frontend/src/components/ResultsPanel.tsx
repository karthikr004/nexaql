import { useState, useCallback } from 'react';
import type { NodeShape, ColumnMeta } from '../types';

interface Props {
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  rowCount: number;
  durationMs: number;
  error: string | null;
  warnings: string[];
  isLoading: boolean;
  isIdle: boolean;
  shape?: NodeShape;
}

const PREVIEW_LIMIT = 5;

// ── Helpers ───────────────────────────────────────────────────────────────────

function cellStyle(type: string, value: unknown): React.CSSProperties {
  if (value === null || value === undefined) return { color: 'var(--text-secondary)' };
  if (type === 'boolean') return { color: '#c084fc' };
  if (['integer', 'bigint', 'smallint', 'numeric', 'float4', 'float8'].includes(type))
    return { color: 'var(--success)' };
  return { color: 'var(--text-primary)' };
}

function cellValue(value: unknown): string {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** "invoice_header__invoice_number" → "invoice_header.invoice_number" */
function displayColName(name: string): string {
  return name.replace(/__/g, '.');
}

// ── Nested JSON builder ───────────────────────────────────────────────────────

type NestedRow = Record<string, unknown>;

function nestRows(rows: Record<string, unknown>[], shape: NodeShape): NestedRow[] {
  if (rows.length === 0) return [];

  const keyColumns = [...shape.columnAliases, ...shape.aggregationAliases];

  const groups = new Map<string, Record<string, unknown>[]>();
  for (const row of rows) {
    const key = keyColumns.map((c) => String(row[c] ?? '\x00')).join('\x01');
    const existing = groups.get(key);
    if (existing) existing.push(row);
    else groups.set(key, [row]);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0]!;
    const result: NestedRow = {};

    for (const alias of shape.columnAliases) {
      const fieldName = alias.includes('__') ? alias.slice(alias.indexOf('__') + 2) : alias;
      result[fieldName] = first[alias];
    }
    for (const agg of shape.aggregationAliases) {
      result[agg] = first[agg];
    }
    for (const child of shape.children) {
      const childKey = child.edgeName ?? child.node;
      result[childKey] = nestRows(groupRows, child);
    }
    return result;
  });
}

// ── JSON syntax highlighter ───────────────────────────────────────────────────

const JSON_COLORS = {
  key: '#7dd3fc', // sky-300    — object keys
  string: '#86efac', // green-300  — string values
  number: '#fbbf24', // amber-400  — numbers
  bool: '#c084fc', // purple-400 — true / false
  null: '#64748b', // slate-500  — null
  punct: '#94a3b8', // slate-400  — { } [ ] : ,
};

function highlightJson(json: string): string {
  const escaped = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // First pass: highlight tokens (strings, numbers, keywords)
  const tokenized = escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          const key = match.slice(0, -1);
          return `<span style="color:${JSON_COLORS.key}">${key}</span><span style="color:${JSON_COLORS.punct}">:</span>`;
        }
        return `<span style="color:${JSON_COLORS.string}">${match}</span>`;
      }
      if (/true|false/.test(match)) return `<span style="color:${JSON_COLORS.bool}">${match}</span>`;
      if (/null/.test(match)) return `<span style="color:${JSON_COLORS.null}">${match}</span>`;
      return `<span style="color:${JSON_COLORS.number}">${match}</span>`;
    },
  );

  // Second pass: colour punctuation characters outside of spans
  return tokenized.replace(/(?<=>|^)([^<]*)(?=<|$)/g, (chunk) =>
    chunk.replace(/([{}[\],])/g, `<span style="color:${JSON_COLORS.punct}">$1</span>`),
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ResultsPanel({
  rows,
  columns,
  rowCount,
  durationMs,
  error,
  warnings,
  isLoading,
  isIdle,
  shape,
}: Props) {
  const [activeTab, setActiveTab] = useState<'table' | 'json'>('table');
  const [copied, setCopied] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const nestedRows = rows.length > 0 && shape ? nestRows(rows, shape) : null;
  const jsonText = nestedRows
    ? JSON.stringify(nestedRows, null, 2)
    : JSON.stringify(
        rows.map((r) => {
          const clean: Record<string, unknown> = {};
          for (const [k, v] of Object.entries(r)) clean[displayColName(k)] = v;
          return clean;
        }),
        null,
        2,
      );

  const copyJson = useCallback(() => {
    navigator.clipboard.writeText(jsonText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [jsonText]);

  const displayedRows = showAll ? rows : rows.slice(0, PREVIEW_LIMIT);
  const hasMore = rows.length > PREVIEW_LIMIT;

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* ── Status bar ─────────────────────────────────────────────── */}
      <div
        className="flex shrink-0 items-center justify-between border-b px-3 py-2"
        style={{ borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2.5">
          <span
            className="font-semibold text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            Results
          </span>
          {!isIdle && !isLoading && !error && (
            <>
              <span
                className="rounded-full border px-2 py-0.5 font-mono text-[11px]"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                }}
              >
                {rowCount.toLocaleString()} rows
              </span>
              <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {durationMs}ms
              </span>
            </>
          )}
          {isLoading && (
            <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              <div
                className="h-3 w-3 animate-spin rounded-full border border-t-transparent"
                style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }}
              />
              Running…
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {rows.length > 0 && (
            <div className="flex overflow-hidden rounded border" style={{ borderColor: 'var(--border)' }}>
              {(['table', 'json'] as const).map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className="px-2.5 py-1 text-[10px] transition-colors"
                  style={
                    activeTab === t
                      ? { backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }
                      : { color: 'var(--text-muted)' }
                  }
                >
                  {t === 'table' ? '⊞ Table' : '{ } JSON'}
                </button>
              ))}
            </div>
          )}
          {rows.length > 0 && activeTab === 'table' && (
            <button
              type="button"
              onClick={() => downloadCSV(rows, columns)}
              className="rounded border px-2 py-1 text-[10px] transition-colors"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
              }}
            >
              ↓ CSV
            </button>
          )}
          {rows.length > 0 && activeTab === 'json' && (
            <button
              type="button"
              onClick={copyJson}
              className="rounded border px-2 py-1 text-[10px] transition-colors"
              style={
                copied
                  ? { borderColor: 'var(--success)', color: 'var(--success)', backgroundColor: 'var(--bg-elevated)' }
                  : { borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }
              }
            >
              {copied ? '✓ Copied' : '⎘ Copy'}
            </button>
          )}
        </div>
      </div>

      {/* ── Warnings ────────────────────────────────────────────────── */}
      {warnings.length > 0 && (
        <div className="shrink-0 border-b px-3 py-2" style={{ backgroundColor: 'var(--bg-warning)', borderColor: 'var(--border-warning)' }}>
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[11px]" style={{ color: 'var(--text-warning)' }}>
              <span>⚠</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Content ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto">
        {isIdle && (
          <div
            className="flex h-full flex-col items-center justify-center gap-2"
            style={{ color: 'var(--text-secondary)' }}
          >
            <span className="text-3xl">⬡</span>
            <p className="text-sm">Run a query to see results</p>
            <p className="text-xs">Press ⌘↩ or click Run</p>
          </div>
        )}

        {error && (
          <div className="fade-in m-3 rounded-lg border p-3" style={{ backgroundColor: 'var(--bg-error)', borderColor: 'var(--border-error)' }}>
            <p className="mb-1 font-semibold text-[11px]" style={{ color: 'var(--text-error)' }}>Error</p>
            <pre className="whitespace-pre-wrap font-mono text-[11px]" style={{ color: 'var(--text-error)' }}>{error}</pre>
          </div>
        )}

        {!isIdle && !error && rows.length === 0 && !isLoading && (
          <div className="flex h-full items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>
            No rows returned
          </div>
        )}

        {/* ── Flat table ──────────────────────────────────────────── */}
        {!isIdle && !error && rows.length > 0 && activeTab === 'table' && (
          <div className="fade-in">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                  {columns.map((col) => (
                    <th
                      key={col.name}
                      className="max-w-[220px] px-3 py-2.5 text-left font-mono font-semibold text-[12px]"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      <span
                        className="block overflow-hidden text-ellipsis whitespace-nowrap"
                        title={displayColName(col.name)}
                      >
                        {displayColName(col.name)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayedRows.map((row, i) => (
                  <tr
                    key={i}
                    className="result-row border-b"
                    style={{ borderColor: 'var(--border)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-secondary)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '')}
                  >
                    {columns.map((col) => {
                      const val = row[col.name];
                      const text = cellValue(val);
                      const isNull = val === null || val === undefined;
                      return (
                        <td
                          key={col.name}
                          className={`max-w-[220px] px-3 py-2.5 font-mono text-[12px]${isNull ? ' italic' : ''}`}
                          title={text}
                          style={cellStyle(col.type, val)}
                        >
                          <span className="block overflow-hidden text-ellipsis whitespace-nowrap">{text}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>

            {/* ── Show all / collapse ─────────────────────────────── */}
            {hasMore && (
              <button
                type="button"
                onClick={() => setShowAll((s) => !s)}
                className="w-full border-t py-2.5 text-center text-[12px] transition-colors"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-secondary)';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }}
              >
                {showAll ? `▲ Show first ${PREVIEW_LIMIT} rows` : `▼ Show all ${rowCount.toLocaleString()} rows`}
              </button>
            )}
          </div>
        )}

        {/* ── JSON view ──────────────────────────────────────────── */}
        {!isIdle && !error && rows.length > 0 && activeTab === 'json' && (
          <div className="fade-in h-full">
            <pre
              className="h-full overflow-auto whitespace-pre p-4 font-mono text-[12px] leading-relaxed"
              style={{ tabSize: 2 }}
              dangerouslySetInnerHTML={{ __html: highlightJson(jsonText) }}
            />
          </div>
        )}
      </div>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      {rows.length > 0 && (
        <div
          className="flex shrink-0 items-center gap-3 border-t px-3 py-1.5"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}
        >
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{columns.length} columns</span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{rowCount.toLocaleString()} rows</span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{durationMs}ms</span>
          {activeTab === 'json' && nestedRows && (
            <span className="text-[10px]" style={{ color: 'var(--accent)' }}>
              ↳ nested · {nestedRows.length} root object{nestedRows.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ── CSV export ────────────────────────────────────────────────────────────────

function downloadCSV(rows: Record<string, unknown>[], columns: ColumnMeta[]) {
  const header = columns.map((c) => displayColName(c.name)).join(',');
  const body = rows
    .map((row) =>
      columns
        .map((c) => {
          const v = row[c.name];
          const s = v === null || v === undefined ? '' : String(v);
          return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
        })
        .join(','),
    )
    .join('\n');
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement('a'), { href: url, download: 'nexaql-results.csv' }).click();
  URL.revokeObjectURL(url);
}
