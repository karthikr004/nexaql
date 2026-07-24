import { useState } from 'react';
import type { NodeInfo } from '../../types';

type SchemaTab = 'fields' | 'edges' | 'filters';

interface SchemaExplorerProps {
  nodes: NodeInfo[];
  onInsert: (text: string) => void;
}

export default function SchemaExplorer({ nodes, onInsert }: SchemaExplorerProps) {
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
