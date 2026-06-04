import { useState } from 'react';
import type { HistoryEntry } from '../types';

interface Props {
  entries: HistoryEntry[];
  onLoad: (query: string) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
}

function timeAgo(ts: number): string {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Return the first non-comment, non-empty line of the query for preview */
function queryPreview(query: string): string {
  const lines = query
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));
  return lines[0]?.slice(0, 80) ?? '';
}

export default function HistoryPanel({ entries, onLoad, onDelete, onClear }: Props) {
  const [confirmClear, setConfirmClear] = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  if (entries.length === 0) {
    return (
      <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div
          className="shrink-0 border-b px-3 pt-3 pb-2"
          style={{ borderColor: 'var(--border)' }}
        >
          <span
            className="font-semibold text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            Query History
          </span>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-2" style={{ color: 'var(--text-secondary)' }}>
          <span className="text-2xl">⏱</span>
          <p className="text-xs">No queries run yet</p>
          <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Run a query to build history</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <div
        className="flex shrink-0 items-center justify-between border-b px-3 pt-3 pb-2"
        style={{ borderColor: 'var(--border)' }}
      >
        <span
          className="font-semibold text-[10px] uppercase tracking-widest"
          style={{ color: 'var(--text-secondary)' }}
        >
          Query History
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>{entries.length} queries</span>
          {confirmClear ? (
            <div className="flex items-center gap-1">
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Clear all?</span>
              <button
                type="button"
                onClick={() => {
                  onClear();
                  setConfirmClear(false);
                }}
                className="rounded border border-red-900/50 bg-red-950/40 px-1.5 py-0.5 text-[10px] text-red-400 transition-colors hover:bg-red-900/40"
              >
                Yes
              </button>
              <button
                type="button"
                onClick={() => setConfirmClear(false)}
                className="rounded border px-1.5 py-0.5 text-[10px] transition-colors"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-secondary)',
                }}
              >
                No
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              className="text-[10px] transition-colors"
              style={{ color: 'var(--text-secondary)' }}
              title="Clear all history"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Entry list */}
      <div className="flex-1 overflow-y-auto">
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="relative border-b transition-colors"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: hoveredId === entry.id ? 'var(--bg-input)' : undefined,
            }}
            onMouseEnter={() => setHoveredId(entry.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            {/* Main click area -> load query */}
            <button
              type="button"
              className="w-full px-3 py-2.5 pr-8 text-left"
              onClick={() => onLoad(entry.query)}
              title="Click to load this query"
            >
              {/* Top row: name + meta */}
              <div className="mb-0.5 flex items-center gap-2">
                <span
                  className="truncate font-mono font-semibold text-[11px]"
                  style={{ color: entry.hadError ? '#f87171' : 'var(--accent)' }}
                >
                  {entry.queryName}
                </span>
                <span
                  className="ml-auto shrink-0 text-[9px]"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {timeAgo(entry.timestamp)}
                </span>
              </div>

              {/* Preview line */}
              <p
                className="truncate font-mono text-[10px] leading-snug"
                style={{ color: 'var(--text-muted)' }}
              >
                {queryPreview(entry.query)}
              </p>

              {/* Bottom meta */}
              <div className="mt-1 flex items-center gap-2">
                {entry.hadError ? (
                  <span className="text-[9px] text-red-500">✗ error</span>
                ) : (
                  <>
                    {entry.rowCount !== undefined && (
                      <span className="text-[9px]" style={{ color: 'var(--success)' }}>
                        {entry.rowCount} rows
                      </span>
                    )}
                    {entry.durationMs !== undefined && (
                      <span className="text-[9px]" style={{ color: 'var(--text-secondary)' }}>
                        {entry.durationMs}ms
                      </span>
                    )}
                  </>
                )}
              </div>
            </button>

            {/* Delete button (appears on hover) */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(entry.id);
              }}
              className={`absolute top-2.5 right-2 text-[11px] transition-colors hover:text-red-400 ${
                hoveredId === entry.id ? 'opacity-100' : 'opacity-0'
              }`}
              style={{ color: 'var(--text-muted)' }}
              title="Remove from history"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
