import type { HistoryEntry } from '../../types';

interface HistoryPanelProps {
  history: HistoryEntry[];
  onLoad: (query: string) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
}

export default function HistoryPanel({ history, onLoad, onDelete, onClear }: HistoryPanelProps) {
  if (history.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
        No queries yet
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--v2-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>{history.length} queries</span>
        <button type="button" onClick={onClear} className="v2-btn v2-btn-ghost v2-btn-sm" style={{ fontSize: 10, color: 'var(--v2-text-tertiary)' }}>Clear all</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {history.map((h) => (
          <div
            key={h.id}
            style={{ padding: '8px 14px', borderBottom: '1px solid var(--v2-border-light)', cursor: 'pointer' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'none'; }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <button
                type="button"
                onClick={() => onLoad(h.query)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                  fontFamily: 'var(--v2-font-mono)', fontSize: 12, fontWeight: 500,
                  color: h.hadError ? 'var(--v2-red-500)' : 'var(--v2-text-primary)',
                  padding: 0, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {h.queryName}
              </button>
              <button
                type="button"
                onClick={() => onDelete(h.id)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--v2-text-tertiary)', fontSize: 10, padding: '2px 4px', flexShrink: 0 }}
              >
                ✕
              </button>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 2, fontSize: 10, color: 'var(--v2-text-tertiary)' }}>
              {h.rowCount !== undefined && <span>{h.rowCount} rows</span>}
              {h.durationMs !== undefined && <span>{h.durationMs}ms</span>}
              <span>{new Date(h.timestamp).toLocaleTimeString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
