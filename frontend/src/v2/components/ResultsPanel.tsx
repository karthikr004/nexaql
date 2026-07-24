import { useState } from 'react';
import type { ExecuteResult } from '../../types';
import { nestRows, downloadCSV, cellValue, cellColor } from '../utils/data';
import { highlightJson } from '../utils/formatters';

interface ResultsPanelProps {
  result: ExecuteResult | null;
  isRunning: boolean;
  isIdle: boolean;
}

const PREVIEW_LIMIT = 5;

export default function ResultsPanel({ result, isRunning, isIdle }: ResultsPanelProps) {
  const [tab, setTab] = useState<'table' | 'json'>('table');
  const [showAll, setShowAll] = useState(false);
  const [copied, setCopied] = useState(false);

  const rows = result?.rows ?? [];
  const columns = result?.columns ?? [];
  const error = result?.error ?? null;
  const warnings = result?.warnings ?? [];
  const rowCount = result?.rowCount ?? 0;
  const durationMs = result?.durationMs ?? 0;
  const shape = result?.shape;

  const displayedRows = showAll ? rows : rows.slice(0, PREVIEW_LIMIT);
  const hasMore = rows.length > PREVIEW_LIMIT;

  const nestedRows = rows.length > 0 && shape ? nestRows(rows, shape) : null;
  const jsonText = nestedRows
    ? JSON.stringify(nestedRows, null, 2)
    : JSON.stringify(rows.map((r) => {
        const clean: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(r)) clean[k.replace(/__/g, '.')] = v;
        return clean;
      }), null, 2);

  const copyJson = () => {
    navigator.clipboard.writeText(jsonText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="v2-label">Results</span>
          {!isIdle && !isRunning && !error && (
            <>
              <span className="v2-badge v2-badge-gray">{rowCount.toLocaleString()} rows</span>
              <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>{durationMs}ms</span>
            </>
          )}
          {isRunning && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--v2-text-tertiary)' }}>
              <div style={{
                width: 12, height: 12, borderRadius: '50%',
                border: '2px solid var(--v2-accent)', borderTopColor: 'transparent',
                animation: 'v2-spin 0.8s linear infinite',
              }} />
              Running...
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {rows.length > 0 && (
            <div style={{ display: 'flex', border: '1px solid var(--v2-border)', borderRadius: 'var(--v2-radius-sm)', overflow: 'hidden' }}>
              {(['table', 'json'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  style={{
                    background: tab === t ? 'var(--v2-bg-hover)' : 'none',
                    border: 'none', cursor: 'pointer', padding: '3px 8px', fontSize: 11,
                    color: tab === t ? 'var(--v2-text-primary)' : 'var(--v2-text-tertiary)',
                  }}
                >
                  {t === 'table' ? 'Table' : 'JSON'}
                </button>
              ))}
            </div>
          )}
          {rows.length > 0 && tab === 'table' && (
            <button type="button" onClick={() => downloadCSV(rows, columns)} className="v2-btn v2-btn-ghost v2-btn-sm" style={{ fontSize: 10 }}>CSV</button>
          )}
          {rows.length > 0 && tab === 'json' && (
            <button type="button" onClick={copyJson} className="v2-btn v2-btn-ghost v2-btn-sm" style={{ fontSize: 10, color: copied ? 'var(--v2-teal-500)' : undefined }}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          )}
        </div>
      </div>

      {warnings.length > 0 && (
        <div style={{ padding: '6px 14px', borderBottom: '1px solid var(--v2-border)', background: 'var(--v2-amber-50)', flexShrink: 0 }}>
          {warnings.map((w, i) => (
            <div key={i} style={{ fontSize: 11, color: 'var(--v2-amber-700)', display: 'flex', gap: 4, alignItems: 'flex-start' }}>
              <span>!</span><span>{w}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isIdle && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 8, color: 'var(--v2-text-tertiary)' }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span style={{ fontSize: 13 }}>Run a query to see results</span>
            <span style={{ fontSize: 11 }}>Press Cmd+Enter or click Run</span>
          </div>
        )}

        {error && (
          <div style={{ margin: 12, padding: 12, borderRadius: 'var(--v2-radius-md)', border: '1px solid var(--v2-red-500)', background: 'var(--v2-red-50)' }}>
            <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--v2-red-600)', marginBottom: 4 }}>Error</div>
            <pre style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, color: 'var(--v2-red-600)', whiteSpace: 'pre-wrap', margin: 0 }}>{error}</pre>
          </div>
        )}

        {!isIdle && !error && rows.length === 0 && !isRunning && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 13, color: 'var(--v2-text-tertiary)' }}>
            No rows returned
          </div>
        )}

        {!isIdle && !error && rows.length > 0 && tab === 'table' && (
          <div style={{ overflowX: 'auto' }}>
            <table className="v2-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col.name} style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={col.name.replace(/__/g, '.')}>
                      {col.name.replace(/__/g, '.')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayedRows.map((row, i) => (
                  <tr key={i}>
                    {columns.map((col) => {
                      const val = row[col.name];
                      const text = cellValue(val);
                      return (
                        <td key={col.name} style={{
                          fontFamily: 'var(--v2-font-mono)', fontSize: 12,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          color: cellColor(col.type, val),
                          fontStyle: val === null || val === undefined ? 'italic' : 'normal',
                        }} title={text}>
                          {text}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            {hasMore && (
              <button
                type="button"
                onClick={() => setShowAll((s) => !s)}
                style={{
                  width: '100%', padding: '8px', textAlign: 'center', fontSize: 12,
                  color: 'var(--v2-text-secondary)', background: 'none', border: 'none',
                  borderTop: '1px solid var(--v2-border)', cursor: 'pointer',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'none'; }}
              >
                {showAll ? `Show first ${PREVIEW_LIMIT} rows` : `Show all ${rowCount.toLocaleString()} rows`}
              </button>
            )}
          </div>
        )}

        {!isIdle && !error && rows.length > 0 && tab === 'json' && (
          <pre
            style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, lineHeight: 1.6, padding: 14, margin: 0, tabSize: 2, overflowX: 'auto' }}
            dangerouslySetInnerHTML={{ __html: highlightJson(jsonText) }}
          />
        )}
      </div>

      {rows.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '4px 14px',
          borderTop: '1px solid var(--v2-border)', fontSize: 10, color: 'var(--v2-text-tertiary)', flexShrink: 0,
        }}>
          <span>{columns.length} columns</span>
          <span>{rowCount.toLocaleString()} rows</span>
          <span>{durationMs}ms</span>
          {tab === 'json' && nestedRows && (
            <span style={{ color: 'var(--v2-accent)' }}>nested · {nestedRows.length} root objects</span>
          )}
        </div>
      )}
    </div>
  );
}
