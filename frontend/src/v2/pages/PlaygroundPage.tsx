import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { useDomain } from '../contexts/DomainContext';
import { useTheme } from '../../ThemeContext';
import type {
  OntologySummary,
  NodeInfo,
  ExecuteResult,
  ValidationState,
  HistoryEntry,
  ColumnMeta,
  NodeShape,
} from '../../types';

const QueryEditor = lazy(() => import('../../components/QueryEditor'));

const HISTORY_KEY = 'nexaql-v2-query-history';
const MAX_HISTORY = 50;

function parseQueryName(query: string): string {
  const m = query.match(/query\s+([A-Za-z_]\w*)/);
  return m?.[1] ?? '(unnamed)';
}

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries: HistoryEntry[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
  } catch { /* ignore */ }
}

const WELCOME_QUERY = `# Welcome to NexaQL Playground
# ─────────────────────────────────────────────
# Write NexaQL queries and execute them against your data.
#
# Try: select an example above, or start typing below.
# ⌘↩ (Ctrl+Enter) to run  ·  click field names to insert
`;

const ROLE_CONFIGS: Record<string, { label: string; roles: string[]; user_id: string; attributes: Record<string, string> }> = {
  anonymous: { label: 'Anonymous', roles: [], user_id: 'anonymous', attributes: {} },
  analyst: { label: 'Analyst (bob)', roles: ['analyst'], user_id: 'bob', attributes: {
    name: 'Bob Smith', email: 'bob@company.com', manager_id: 'mgr-east', region: 'US-EAST',
    department: 'Engineering', team_id: 'eng-platform', level: 'L4', job_role: 'Software Engineer',
  }},
  manager: { label: 'Manager (alice)', roles: ['manager'], user_id: 'alice', attributes: {
    name: 'Alice Johnson', email: 'alice@company.com', manager_id: 'mgr-east', region: 'US-EAST',
    department: 'Engineering', team_id: 'eng-platform', level: 'L6', job_role: 'Engineering Manager',
  }},
  admin: { label: 'Admin (full)', roles: ['admin'], user_id: 'admin', attributes: {} },
};

// ── SQL syntax highlighter ──────────────────────────────────────────────────

function highlightSQL(sql: string): string {
  const keywords = [
    'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'INNER JOIN',
    'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET', 'ON',
    'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'AS', 'DISTINCT',
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'EXISTS', 'INTERVAL',
    'CURRENT_DATE', 'TRUE', 'FALSE',
  ];
  let out = sql.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  out = out.replace(/'[^']*'/g, (m) => `\x00STR${m}\x00END`);
  for (const kw of keywords) {
    out = out.replace(new RegExp(`\\b${kw}\\b`, 'g'), `\x00KW${kw}\x00END`);
  }
  out = out.replace(/\b(\d+)\b/g, `\x00NUM$1\x00END`);
  out = out.replace(/\b([a-z][a-z0-9]*)\./g, `\x00AL$1\x00END.`);
  out = out.replace(/\x00KW(.*?)\x00END/g, '<span style="color:#a78bfa;font-weight:600">$1</span>');
  out = out.replace(/\x00STR(.*?)\x00END/g, '<span style="color:#fb923c">$1</span>');
  out = out.replace(/\x00NUM(.*?)\x00END/g, '<span style="color:#22d3ee">$1</span>');
  out = out.replace(/\x00AL(.*?)\x00END/g, '<span style="color:var(--v2-text-tertiary)">$1</span>');
  return out;
}

function highlightURL(url: string): string {
  let out = url.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  out = out.replace(/^(GET|POST)\s+(.+)$/, (_, method, rest) => {
    const qIdx = rest.indexOf('?');
    if (qIdx === -1) {
      return `<span style="color:var(--v2-purple-400);font-weight:600">${method}</span> <span style="color:var(--v2-accent)">${rest}</span>`;
    }
    const path = rest.slice(0, qIdx);
    const params = rest.slice(qIdx + 1).split('&amp;').map((p: string) => {
      const [k, v] = p.split('=');
      return `<span style="color:#22d3ee">${k}</span>=<span style="color:#fb923c">${v ?? ''}</span>`;
    }).join(`<span style="color:var(--v2-text-secondary)">&amp;</span>`);
    return `<span style="color:var(--v2-purple-400);font-weight:600">${method}</span> <span style="color:var(--v2-accent)">${path}</span><span style="color:var(--v2-text-secondary)">?</span>${params}`;
  });
  return out;
}

// ── JSON highlighter ────────────────────────────────────────────────────────

const JSON_COLORS = {
  key: '#7dd3fc',
  string: '#86efac',
  number: '#fbbf24',
  bool: '#c084fc',
  null: '#64748b',
  punct: '#94a3b8',
};

function highlightJson(json: string): string {
  const escaped = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
  return tokenized.replace(/(?<=>|^)([^<]*)(?=<|$)/g, (chunk) =>
    chunk.replace(/([{}[\],])/g, `<span style="color:${JSON_COLORS.punct}">$1</span>`),
  );
}

// ── Nested JSON builder ─────────────────────────────────────────────────────

function nestRows(rows: Record<string, unknown>[], shape: NodeShape): Record<string, unknown>[] {
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
    const result: Record<string, unknown> = {};
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

// ── CSV export ──────────────────────────────────────────────────────────────

function downloadCSV(rows: Record<string, unknown>[], columns: ColumnMeta[]) {
  const header = columns.map((c) => c.name.replace(/__/g, '.')).join(',');
  const body = rows.map((row) =>
    columns.map((c) => {
      const v = row[c.name];
      const s = v === null || v === undefined ? '' : String(v);
      return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(','),
  ).join('\n');
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement('a'), { href: url, download: 'nexaql-results.csv' }).click();
  URL.revokeObjectURL(url);
}

// ── Cell helpers ────────────────────────────────────────────────────────────

function cellValue(value: unknown): string {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function cellColor(type: string, value: unknown): string {
  if (value === null || value === undefined) return 'var(--v2-text-tertiary)';
  if (type === 'boolean') return '#c084fc';
  if (['integer', 'bigint', 'smallint', 'numeric', 'float4', 'float8'].includes(type)) return 'var(--v2-teal-500)';
  return 'var(--v2-text-primary)';
}

// ── Schema Explorer ─────────────────────────────────────────────────────────

type SchemaTab = 'fields' | 'edges' | 'filters';

function V2SchemaExplorer({ nodes, onInsert }: { nodes: NodeInfo[]; onInsert: (text: string) => void }) {
  const [search, setSearch] = useState('');
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SchemaTab>('fields');

  const node = selectedNode ? nodes.find((n) => n.name === selectedNode) ?? null : null;

  const filtered = nodes.filter((n) =>
    !search || n.name.toLowerCase().includes(search.toLowerCase()) || n.description.toLowerCase().includes(search.toLowerCase()),
  );

  if (node) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Back + node name */}
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0 }}>
          <button
            type="button"
            onClick={() => setSelectedNode(null)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              fontSize: 12, color: 'var(--v2-accent)', display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back
          </button>
          <div style={{ marginTop: 6 }}>
            <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--v2-text-primary)' }}>{node.name}</span>
            <div style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 2 }}>{node.description}</div>
            <div style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 1, fontFamily: 'var(--v2-font-mono)' }}>{node.table}</div>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--v2-border)', flexShrink: 0, padding: '0 14px' }}>
          {(['fields', 'edges', 'filters'] as const).map((t) => {
            const count = t === 'fields' ? node.fields.length : t === 'edges' ? node.edges.length : node.specialFilters.length;
            const isActive = activeTab === t;
            return (
              <button
                key={t}
                type="button"
                onClick={() => setActiveTab(t)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  padding: '8px 12px', fontSize: 12, fontWeight: 500,
                  color: isActive ? 'var(--v2-accent)' : 'var(--v2-text-tertiary)',
                  borderBottom: isActive ? '2px solid var(--v2-accent)' : '2px solid transparent',
                  textTransform: 'capitalize',
                }}
              >
                {t} <span style={{ opacity: 0.6 }}>{count}</span>
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {activeTab === 'fields' && node.fields.map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => onInsert(f.name)}
              title={f.description}
              style={{
                display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between',
                padding: '6px 14px', background: 'none', border: 'none', cursor: 'pointer',
                textAlign: 'left', fontSize: 12,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'none'; }}
            >
              <span style={{ fontFamily: 'var(--v2-font-mono)', color: f.filterable ? 'var(--v2-teal-500)' : 'var(--v2-text-primary)' }}>
                {f.name}
                {f.filterable && <span style={{ marginLeft: 4, fontSize: 9, color: 'var(--v2-text-tertiary)' }}>filterable</span>}
              </span>
              <span className="v2-badge v2-badge-gray" style={{ fontSize: 10 }}>{f.type}</span>
            </button>
          ))}

          {activeTab === 'edges' && (node.edges.length === 0 ? (
            <div style={{ padding: '16px 14px', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>No edges defined</div>
          ) : node.edges.map((e) => (
            <button
              key={e.name}
              type="button"
              onClick={() => { onInsert(`${e.name} {\n    \n  }`); }}
              title={e.description}
              style={{
                display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between',
                padding: '6px 14px', background: 'none', border: 'none', cursor: 'pointer',
                textAlign: 'left', fontSize: 12,
              }}
              onMouseEnter={(ev) => { ev.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
              onMouseLeave={(ev) => { ev.currentTarget.style.background = 'none'; }}
            >
              <span style={{ fontFamily: 'var(--v2-font-mono)', color: '#fb923c' }}>
                {e.name} <span style={{ color: 'var(--v2-text-tertiary)' }}>→ {e.target}</span>
              </span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          )))}

          {activeTab === 'filters' && (
            <>
              {node.fields.filter((f) => f.filterable).map((f) => (
                <button
                  key={f.name}
                  type="button"
                  onClick={() => onInsert(`${f.name}: `)}
                  title={f.description}
                  style={{
                    display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between',
                    padding: '6px 14px', background: 'none', border: 'none', cursor: 'pointer',
                    textAlign: 'left', fontSize: 12,
                  }}
                  onMouseEnter={(ev) => { ev.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
                  onMouseLeave={(ev) => { ev.currentTarget.style.background = 'none'; }}
                >
                  <span style={{ fontFamily: 'var(--v2-font-mono)', color: '#fbbf24' }}>{f.name}</span>
                  <span className="v2-badge v2-badge-gray" style={{ fontSize: 10 }}>{f.type}</span>
                </button>
              ))}
              {node.specialFilters.map((sf) => (
                <button
                  key={sf.name}
                  type="button"
                  onClick={() => onInsert(sf.type === 'integer' ? `${sf.name}: 30` : `${sf.name}: true`)}
                  title={sf.description}
                  style={{
                    display: 'flex', width: '100%', flexDirection: 'column', alignItems: 'flex-start',
                    padding: '6px 14px', background: 'none', border: 'none', cursor: 'pointer',
                    textAlign: 'left', fontSize: 12,
                  }}
                  onMouseEnter={(ev) => { ev.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
                  onMouseLeave={(ev) => { ev.currentTarget.style.background = 'none'; }}
                >
                  <span style={{ fontFamily: 'var(--v2-font-mono)', color: '#f472b6' }}>
                    {sf.type === 'integer' ? `${sf.name}: 30` : `${sf.name}: true`}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 2 }}>{sf.description}</span>
                </button>
              ))}
              {node.fields.filter((f) => f.filterable).length === 0 && node.specialFilters.length === 0 && (
                <div style={{ padding: '16px 14px', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>No filters defined</div>
              )}
            </>
          )}
        </div>

        {/* Insert template button */}
        <div style={{ padding: '8px 14px', borderTop: '1px solid var(--v2-border)', flexShrink: 0 }}>
          <button
            type="button"
            className="v2-btn v2-btn-secondary v2-btn-sm"
            style={{ width: '100%', fontSize: 11 }}
            onClick={() => {
              const fields = node.fields.slice(0, 5).map((f) => `    ${f.name}`).join('\n');
              onInsert(`query {\n  ${node.name} {\n${fields}\n  }\n}`);
            }}
          >
            Insert query template
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Search */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0 }}>
        <input
          type="text"
          placeholder="Search nodes..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="v2-input"
          style={{ fontSize: 12, padding: '6px 10px' }}
        />
      </div>

      {/* Node list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {filtered.length === 0 && (
          <div style={{ padding: '16px 14px', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>No nodes match "{search}"</div>
        )}
        {filtered.map((n) => (
          <button
            key={n.name}
            type="button"
            onClick={() => { setSelectedNode(n.name); setActiveTab('fields'); }}
            style={{
              display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 14px', background: 'none', border: 'none', borderBottom: '1px solid var(--v2-border-light)',
              cursor: 'pointer', textAlign: 'left',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-bg-hover)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'none'; }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--v2-accent-text)' }}>{n.name}</div>
              <div style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.description}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, marginLeft: 8 }}>
              <span style={{ fontSize: 10, color: 'var(--v2-text-tertiary)' }}>{n.fieldCount}f · {n.edges.length}e</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── History Panel ────────────────────────────────────────────────────────────

function V2HistoryPanel({ history, onLoad, onDelete, onClear }: {
  history: HistoryEntry[];
  onLoad: (query: string) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
}) {
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
            style={{
              padding: '8px 14px', borderBottom: '1px solid var(--v2-border-light)',
              cursor: 'pointer',
            }}
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

// ── Results Panel ───────────────────────────────────────────────────────────

function V2ResultsPanel({ result, isRunning, isIdle }: { result: ExecuteResult | null; isRunning: boolean; isIdle: boolean }) {
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

  const PREVIEW_LIMIT = 5;
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
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 14px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0,
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

      {/* Warnings */}
      {warnings.length > 0 && (
        <div style={{ padding: '6px 14px', borderBottom: '1px solid var(--v2-border)', background: 'var(--v2-amber-50)', flexShrink: 0 }}>
          {warnings.map((w, i) => (
            <div key={i} style={{ fontSize: 11, color: 'var(--v2-amber-700)', display: 'flex', gap: 4, alignItems: 'flex-start' }}>
              <span>!</span><span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
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

        {/* Table view */}
        {!isIdle && !error && rows.length > 0 && tab === 'table' && (
          <div>
            <table className="v2-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col.name} style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={col.name.replace(/__/g, '.')}>
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
                          maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
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

        {/* JSON view */}
        {!isIdle && !error && rows.length > 0 && tab === 'json' && (
          <pre
            style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, lineHeight: 1.6, padding: 14, margin: 0, tabSize: 2 }}
            dangerouslySetInnerHTML={{ __html: highlightJson(jsonText) }}
          />
        )}
      </div>

      {/* Footer */}
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

// ── SQL Preview Panel ───────────────────────────────────────────────────────

const ADAPTER_LABELS: Record<string, { label: string; color: string }> = {
  postgresql: { label: 'PostgreSQL', color: 'var(--v2-teal-500)' },
  mysql: { label: 'MySQL', color: '#f97316' },
  mongodb: { label: 'MongoDB', color: 'var(--v2-teal-500)' },
  rest: { label: 'REST API', color: 'var(--v2-purple-400)' },
};

function V2SQLPreview({ queryPreview, adapterType, isLoading }: { queryPreview: string | null; adapterType: string | null; isLoading: boolean }) {
  const [copied, setCopied] = useState(false);

  const isREST = adapterType === 'rest';
  const meta = adapterType ? (ADAPTER_LABELS[adapterType] ?? { label: adapterType, color: 'var(--v2-teal-500)' }) : { label: 'SQL', color: 'var(--v2-teal-500)' };
  const highlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;

  const copy = () => {
    if (!queryPreview) return;
    navigator.clipboard.writeText(queryPreview).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 14px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="v2-label">{isREST ? 'Request Preview' : 'SQL Preview'}</span>
          <span className="v2-badge v2-badge-gray" style={{ fontSize: 10, color: meta.color }}>{meta.label}</span>
        </div>
        {queryPreview && (
          <button type="button" onClick={copy} className="v2-btn v2-btn-ghost v2-btn-sm" style={{ fontSize: 10, color: copied ? 'var(--v2-teal-500)' : undefined }}>
            {copied ? 'Copied' : 'Copy'}
          </button>
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
        {isLoading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
            <div style={{
              width: 12, height: 12, borderRadius: '50%',
              border: '2px solid var(--v2-accent)', borderTopColor: 'transparent',
              animation: 'v2-spin 0.8s linear infinite',
            }} />
            Translating...
          </div>
        )}
        {!isLoading && !queryPreview && (
          <div style={{ textAlign: 'center', marginTop: 32, fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
            {isREST ? 'Write a REST query to see the request' : 'Write a query to see the generated SQL'}
          </div>
        )}
        {!isLoading && highlighted && (
          <pre
            style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0, color: 'var(--v2-text-primary)' }}
            dangerouslySetInnerHTML={{ __html: highlighted }}
          />
        )}
      </div>
    </div>
  );
}

// ── Main Playground ─────────────────────────────────────────────────────────

export default function PlaygroundPage() {
  const { activeDomain } = useDomain();
  const { theme } = useTheme();
  const [query, setQuery] = useState(WELCOME_QUERY);
  const initialQuerySet = useRef(false);
  const [insertText, setInsertText] = useState<string | undefined>(undefined);
  const [ontology, setOntology] = useState<OntologySummary | null>(null);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [validation, setValidation] = useState<ValidationState>({ valid: false, errors: [], warnings: [] });
  const [validLoaded, setValidLoaded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isIdle, setIsIdle] = useState(true);
  const [activeRole, setActiveRole] = useState('anonymous');
  const [leftView, setLeftView] = useState<'schema' | 'history'>('schema');
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  // Panel widths (percentages)
  const [leftWidth, setLeftWidth] = useState(22);
  const [rightWidth, setRightWidth] = useState(28);
  const [resultsH, setResultsH] = useState(40);
  const dragRef = useRef<{ type: string; startX: number; startVal: number } | null>(null);

  useEffect(() => { setHistory(loadHistory()); }, []);

  const fetchOntology = useCallback(() => {
    fetch('/api/ontology')
      .then((r) => r.json())
      .then((data) => {
        if (data && Array.isArray(data.nodes)) setOntology(data);
      })
      .catch(() => {});
  }, []);

  useEffect(() => { fetchOntology(); }, [fetchOntology]);

  useEffect(() => {
    const first = ontology?.examples?.[0];
    if (first && !initialQuerySet.current) {
      initialQuerySet.current = true;
      setQuery(first.query);
    }
  }, [ontology]);

  const userContextHeaders = useCallback((): Record<string, string> => {
    const cfg = ROLE_CONFIGS[activeRole];
    if (!cfg) return {};
    return {
      'X-User-Context': JSON.stringify({
        user_id: cfg.user_id,
        roles: cfg.roles,
        ...cfg.attributes,
      }),
    };
  }, [activeRole]);

  const prevRoleRef = useRef(activeRole);
  useEffect(() => {
    if (prevRoleRef.current !== activeRole) {
      prevRoleRef.current = activeRole;
      setResult(null);
      setValidLoaded(false);
      setIsIdle(true);
    }
  }, [activeRole]);

  const validateSeqRef = useRef(0);
  useEffect(() => {
    const seq = ++validateSeqRef.current;
    const delay = 400;
    const headers = userContextHeaders();
    const t = setTimeout(() => {
      if (!query.trim()) return;
      fetch('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ query }),
      })
        .then((r) => r.json())
        .then((v) => {
          if (seq === validateSeqRef.current) {
            setValidation(v);
            setValidLoaded(true);
          }
        })
        .catch(() => {});
    }, delay);
    return () => clearTimeout(t);
  }, [query, activeRole, userContextHeaders]);

  const addToHistory = useCallback((entry: HistoryEntry) => {
    setHistory((prev) => {
      const next = [entry, ...prev.filter((h) => h.query.trim() !== entry.query.trim())].slice(0, MAX_HISTORY);
      saveHistory(next);
      return next;
    });
  }, []);

  const runQuery = useCallback(async () => {
    if (!query.trim() || isRunning) return;
    setIsRunning(true);
    setIsIdle(false);
    const t0 = Date.now();
    try {
      const res = await fetch('/api/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...userContextHeaders() },
        body: JSON.stringify({ query }),
      });
      const data: ExecuteResult = await res.json();
      setResult(data);
      addToHistory({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        query,
        queryName: parseQueryName(query),
        timestamp: Date.now(),
        rowCount: data.error ? undefined : (data.rowCount ?? 0),
        durationMs: Date.now() - t0,
        hadError: !!data.error,
      });
    } catch (e) {
      setResult({ error: String(e), rows: [], columns: [] });
      addToHistory({
        id: `${Date.now()}-err`,
        query,
        queryName: parseQueryName(query),
        timestamp: Date.now(),
        hadError: true,
      });
    } finally {
      setIsRunning(false);
    }
  }, [query, isRunning, userContextHeaders, addToHistory]);

  const startHDrag = (type: 'left' | 'right', e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { type, startX: e.clientX, startVal: type === 'left' ? leftWidth : rightWidth };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = ((ev.clientX - dragRef.current.startX) / window.innerWidth) * 100;
      if (dragRef.current.type === 'left') setLeftWidth(Math.min(35, Math.max(15, dragRef.current.startVal + delta)));
      else setRightWidth(Math.min(40, Math.max(18, dragRef.current.startVal - delta)));
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startVDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = resultsH;
    const onMove = (ev: MouseEvent) => {
      const delta = -((ev.clientY - startY) / window.innerHeight) * 100;
      setResultsH(Math.min(70, Math.max(15, startH + delta)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const centerWidth = 100 - leftWidth - rightWidth;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--v2-bg-app)', overflow: 'hidden' }}>
      {/* Top toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', borderBottom: '1px solid var(--v2-border)',
        background: 'var(--v2-bg-surface)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="v2-heading-sm">Query Playground</span>
          {activeDomain && <span className="v2-badge v2-badge-purple">{activeDomain}</span>}
          {validLoaded && (
            validation.valid
              ? <span style={{ fontSize: 11, color: 'var(--v2-teal-500)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  Valid
                </span>
              : <span style={{ fontSize: 11, color: 'var(--v2-red-500)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {validation.errors[0]?.slice(0, 60)}
                </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>Role:</span>
            <select
              value={activeRole}
              onChange={(e) => setActiveRole(e.target.value)}
              style={{
                appearance: 'none', background: 'var(--v2-bg-input)', border: '1px solid var(--v2-border)',
                borderRadius: 'var(--v2-radius-sm)', padding: '4px 24px 4px 8px', fontSize: 12,
                color: 'var(--v2-text-primary)', cursor: 'pointer', outline: 'none',
                backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%236B7280' stroke-width='2'%3e%3cpolyline points='6 9 12 15 18 9'/%3e%3c/svg%3e")`,
                backgroundRepeat: 'no-repeat', backgroundPosition: 'right 6px center',
              }}
            >
              {Object.entries(ROLE_CONFIGS).map(([key, cfg]) => (
                <option key={key} value={key}>{cfg.label}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={runQuery}
            disabled={isRunning || !query.trim()}
            className="v2-btn v2-btn-primary v2-btn-sm"
            style={{ gap: 4, opacity: isRunning || !query.trim() ? 0.5 : 1 }}
          >
            {isRunning ? (
              <div style={{
                width: 12, height: 12, borderRadius: '50%',
                border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white',
                animation: 'v2-spin 0.8s linear infinite',
              }} />
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3" /></svg>
            )}
            {isRunning ? 'Running...' : 'Run'}
          </button>
        </div>
      </div>

      {/* Main three-panel layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left panel: Schema / History */}
        <div style={{ width: `${leftWidth}%`, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--v2-border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', borderBottom: '1px solid var(--v2-border)', flexShrink: 0 }}>
            {(['schema', 'history'] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setLeftView(v)}
                style={{
                  flex: 1, background: 'none', border: 'none', cursor: 'pointer',
                  padding: '8px 0', fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em',
                  color: leftView === v ? 'var(--v2-accent)' : 'var(--v2-text-tertiary)',
                  borderBottom: leftView === v ? '2px solid var(--v2-accent)' : '2px solid transparent',
                }}
              >
                {v === 'schema' ? 'Schema' : 'History'}
                {v === 'history' && history.length > 0 && (
                  <span style={{ marginLeft: 4, opacity: 0.6 }}>{history.length}</span>
                )}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            {leftView === 'schema' && ontology ? (
              <V2SchemaExplorer nodes={ontology.nodes} onInsert={(text) => setInsertText(text)} />
            ) : leftView === 'schema' ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                Loading schema...
              </div>
            ) : (
              <V2HistoryPanel
                history={history}
                onLoad={(q) => { setQuery(q); setLeftView('schema'); }}
                onDelete={(id) => {
                  setHistory((prev) => {
                    const next = prev.filter((h) => h.id !== id);
                    saveHistory(next);
                    return next;
                  });
                }}
                onClear={() => { setHistory([]); saveHistory([]); }}
              />
            )}
          </div>
        </div>

        {/* Left resize handle */}
        <div
          style={{ width: 4, cursor: 'col-resize', background: 'transparent', flexShrink: 0 }}
          onMouseDown={(e) => startHDrag('left', e)}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-accent-subtle)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        />

        {/* Center panel: Editor + Results (stacked) */}
        <div style={{ width: `${centerWidth}%`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div className="v2-legacy-bridge" style={{ height: `${100 - resultsH}%`, borderBottom: '1px solid var(--v2-border)', overflow: 'hidden' }}>
            <Suspense fallback={
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                Loading editor...
              </div>
            }>
              <QueryEditor
                value={query}
                onChange={setQuery}
                onRun={runQuery}
                insertText={insertText}
                onInsertConsumed={() => setInsertText(undefined)}
                ontologyNodes={ontology?.nodes ?? []}
                examples={ontology?.examples}
                theme={theme}
              />
            </Suspense>
          </div>

          {/* Vertical resize handle */}
          <div
            style={{ height: 4, cursor: 'row-resize', background: 'transparent', flexShrink: 0 }}
            onMouseDown={startVDrag}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-accent-subtle)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          />

          <div style={{ height: `${resultsH}%`, overflow: 'hidden' }}>
            <V2ResultsPanel result={result} isRunning={isRunning} isIdle={isIdle} />
          </div>
        </div>

        {/* Right resize handle */}
        <div
          style={{ width: 4, cursor: 'col-resize', background: 'transparent', flexShrink: 0 }}
          onMouseDown={(e) => startHDrag('right', e)}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--v2-accent-subtle)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        />

        {/* Right panel: SQL Preview */}
        <div style={{ width: `${rightWidth}%`, borderLeft: '1px solid var(--v2-border)', overflow: 'hidden', flexShrink: 0 }}>
          <V2SQLPreview
            queryPreview={validation.queryPreview ?? result?.queryPreview ?? null}
            adapterType={validation.adapterType ?? result?.adapterType ?? null}
            isLoading={isRunning}
          />
        </div>
      </div>
    </div>
  );
}
