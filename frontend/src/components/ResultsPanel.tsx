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

function cellClass(type: string, value: unknown): string {
  if (value === null || value === undefined) return 'font-mono text-[12px] text-slate-600 italic';
  if (type === 'boolean') return 'font-mono text-[12px] text-purple-400';
  if (['integer', 'bigint', 'smallint', 'numeric', 'float4', 'float8'].includes(type))
    return 'font-mono text-[12px] text-[#3dd68c]';
  return 'font-mono text-[12px] text-slate-200';
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
    <div className="flex h-full flex-col bg-[#0f1117]">
      {/* ── Status bar ─────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between border-[#252d3d] border-b px-3 py-2">
        <div className="flex items-center gap-2.5">
          <span className="font-semibold text-[10px] text-slate-400 uppercase tracking-widest">Results</span>
          {!isIdle && !isLoading && !error && (
            <>
              <span className="rounded-full border border-[#252d3d] bg-[#1a2233] px-2 py-0.5 font-mono text-[11px] text-slate-300">
                {rowCount.toLocaleString()} rows
              </span>
              <span className="text-[11px] text-slate-500">{durationMs}ms</span>
            </>
          )}
          {isLoading && (
            <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
              <div className="h-3 w-3 animate-spin rounded-full border border-[#4f8ef7] border-t-transparent" />
              Running…
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {rows.length > 0 && (
            <div className="flex overflow-hidden rounded border border-[#252d3d]">
              {(['table', 'json'] as const).map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={`px-2.5 py-1 text-[10px] transition-colors ${
                    activeTab === t ? 'bg-[#1e2535] text-slate-200' : 'text-slate-500 hover:text-slate-300'
                  }`}
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
              className="rounded border border-[#252d3d] bg-[#1e2535] px-2 py-1 text-[10px] text-slate-400 transition-colors hover:text-slate-200"
            >
              ↓ CSV
            </button>
          )}
          {rows.length > 0 && activeTab === 'json' && (
            <button
              type="button"
              onClick={copyJson}
              className={`rounded border border-[#252d3d] bg-[#1e2535] px-2 py-1 text-[10px] transition-colors ${
                copied ? 'border-[#3dd68c] text-[#3dd68c]' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {copied ? '✓ Copied' : '⎘ Copy'}
            </button>
          )}
        </div>
      </div>

      {/* ── Warnings ────────────────────────────────────────────────── */}
      {warnings.length > 0 && (
        <div className="shrink-0 border-yellow-900/30 border-b bg-yellow-950/20 px-3 py-2">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[11px] text-yellow-400">
              <span>⚠</span>
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Content ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto">
        {isIdle && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-slate-600">
            <span className="text-3xl">⬡</span>
            <p className="text-sm">Run a query to see results</p>
            <p className="text-xs">Press ⌘↩ or click Run</p>
          </div>
        )}

        {error && (
          <div className="fade-in m-3 rounded-lg border border-red-900/50 bg-red-950/20 p-3">
            <p className="mb-1 font-semibold text-[11px] text-red-400">Error</p>
            <pre className="whitespace-pre-wrap font-mono text-[11px] text-red-300">{error}</pre>
          </div>
        )}

        {!isIdle && !error && rows.length === 0 && !isLoading && (
          <div className="flex h-full items-center justify-center text-slate-500 text-sm">No rows returned</div>
        )}

        {/* ── Flat table ──────────────────────────────────────────── */}
        {!isIdle && !error && rows.length > 0 && activeTab === 'table' && (
          <div className="fade-in">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-[#252d3d] border-b">
                  {columns.map((col) => (
                    <th
                      key={col.name}
                      className="max-w-[220px] px-3 py-2.5 text-left font-mono font-semibold text-[12px] text-slate-300"
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
                  <tr key={i} className="border-[#1e2535] border-b hover:bg-[#131920]">
                    {columns.map((col) => {
                      const val = row[col.name];
                      const text = cellValue(val);
                      return (
                        <td
                          key={col.name}
                          className={`max-w-[220px] px-3 py-2.5 ${cellClass(col.type, val)}`}
                          title={text}
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
                className="w-full border-[#252d3d] border-t py-2.5 text-center text-[12px] text-slate-400 transition-colors hover:bg-[#131920] hover:text-slate-200"
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
        <div className="flex shrink-0 items-center gap-3 border-[#252d3d] border-t bg-[#0f1117] px-3 py-1.5">
          <span className="text-[10px] text-slate-500">{columns.length} columns</span>
          <span className="text-[10px] text-slate-500">{rowCount.toLocaleString()} rows</span>
          <span className="text-[10px] text-slate-500">{durationMs}ms</span>
          {activeTab === 'json' && nestedRows && (
            <span className="text-[#4f8ef7] text-[10px]">
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
