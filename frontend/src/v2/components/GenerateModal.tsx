import { useState, useCallback } from 'react';
import type { ToastData } from './Toast';

interface ConnectorInfo {
  id?: number;
  name: string;
  db_type: string;
}

interface TableInfoItem {
  name: string;
  schema: string;
  column_count: number;
  primary_key: string | null;
  row_count_estimate: number | null;
}

interface GenerateModalProps {
  connectors: ConnectorInfo[];
  defaultDomain: string;
  lockDomain: boolean;
  onGenerated: () => void;
  onClose: () => void;
  onToast: (t: ToastData) => void;
}

export default function GenerateModal({
  connectors,
  defaultDomain,
  lockDomain,
  onGenerated,
  onClose,
  onToast,
}: GenerateModalProps) {
  const [connector, setConnector] = useState('');
  const [schemaName, setSchemaName] = useState('');
  const [domain, setDomain] = useState(defaultDomain);
  const [description, setDescription] = useState('');
  const [tables, setTables] = useState<TableInfoItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [introspecting, setIntrospecting] = useState(false);
  const [generating, setGenerating] = useState(false);

  const handleIntrospect = useCallback(async () => {
    if (!connector) return;
    setIntrospecting(true);
    setTables([]);
    setSelected(new Set());
    try {
      const res = await fetch(`/api/connectors/${encodeURIComponent(connector)}/introspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema_name: 'public' }),
      });
      const body = await res.json();
      if (res.ok) {
        const t: TableInfoItem[] = body.tables ?? [];
        setTables(t);
        const allNames = new Set<string>();
        for (const item of t) {
          allNames.add(item.name);
        }
        setSelected(allNames);
      } else {
        onToast({ message: body.error || 'Introspection failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setIntrospecting(false);
    }
  }, [connector, onToast]);

  const handleGenerate = useCallback(async () => {
    const name = schemaName.trim() || connector;
    if (!connector || !name) return;
    if (!lockDomain && !domain.trim()) return;
    setGenerating(true);
    try {
      const includeTables = selected.size < tables.length ? Array.from(selected) : undefined;
      const res = await fetch('/api/generate-ontology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connector_name: connector,
          domain: lockDomain ? defaultDomain : domain.trim(),
          description,
          include_tables: includeTables,
          output_schema_name: name,
          replace: false,
        }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: `Schema "${name}" generated (${body.node_count} nodes, ${body.total_fields} fields)`, type: 'success' });
        onGenerated();
      } else {
        onToast({ message: body.error || 'Generation failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setGenerating(false);
    }
  }, [connector, schemaName, domain, defaultDomain, lockDomain, description, selected, tables.length, onGenerated, onToast]);

  const toggleTable = (name: string, checked: boolean) => {
    const next = new Set(selected);
    if (checked) {
      next.add(name);
    } else {
      next.delete(name);
    }
    setSelected(next);
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.5)',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 520,
          maxHeight: '80vh',
          overflowY: 'auto',
          padding: 24,
          borderRadius: 'var(--v2-radius-lg)',
          border: '1px solid var(--v2-border)',
          background: 'var(--v2-bg-elevated)',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <span className="v2-heading-md">
            {lockDomain ? `Add schema to "${defaultDomain}"` : 'New domain'}
          </span>
          <button type="button" onClick={onClose} className="v2-icon-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!lockDomain && (
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Domain name</label>
              <input
                className="v2-input"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="e.g. procurement, ecommerce, hr"
              />
            </div>
          )}

          <div>
            <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>
              {lockDomain ? 'Schema name' : 'Description (optional)'}
            </label>
            {lockDomain ? (
              <input
                className="v2-input"
                value={schemaName}
                onChange={(e) => setSchemaName(e.target.value)}
                placeholder="e.g. products, inventory (defaults to connector name)"
              />
            ) : (
              <input
                className="v2-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Procurement data from production DB"
              />
            )}
          </div>

          {lockDomain && (
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Description (optional)</label>
              <input
                className="v2-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Analytics tables from warehouse"
              />
            </div>
          )}

          <div>
            <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Connector</label>
            {connectors.length === 0 ? (
              <p className="v2-body-sm">No connectors available. Add one in the Connectors page first.</p>
            ) : (
              <select
                className="v2-select"
                value={connector}
                onChange={(e) => { setConnector(e.target.value); setTables([]); setSelected(new Set()); }}
              >
                <option value="">Choose a connector...</option>
                {connectors.map((c) => (
                  <option key={c.name} value={c.name}>{c.name} ({c.db_type})</option>
                ))}
              </select>
            )}
          </div>

          {connector && tables.length === 0 && (
            <button
              type="button"
              onClick={handleIntrospect}
              disabled={introspecting}
              className="v2-btn v2-btn-primary"
              style={{ alignSelf: 'flex-start' }}
            >
              {introspecting ? 'Loading tables...' : 'Load tables'}
            </button>
          )}

          {tables.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="v2-label">Tables ({selected.size}/{tables.length})</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => {
                      const all = new Set<string>();
                      for (const t of tables) { all.add(t.name); }
                      setSelected(all);
                    }}
                    style={{ fontSize: 11, color: 'var(--v2-accent-text)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelected(new Set())}
                    style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                  >
                    None
                  </button>
                </div>
              </div>
              <div
                style={{
                  borderRadius: 'var(--v2-radius-md)',
                  border: '1px solid var(--v2-border)',
                  maxHeight: 200,
                  overflowY: 'auto',
                }}
              >
                {tables.map((t) => (
                  <label
                    key={t.name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 12px',
                      borderBottom: '1px solid var(--v2-border-light)',
                      cursor: 'pointer',
                      fontSize: 13,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(t.name)}
                      onChange={(e) => toggleTable(t.name, e.target.checked)}
                    />
                    <span style={{ fontFamily: 'var(--v2-font-mono)', color: 'var(--v2-text-primary)' }}>{t.name}</span>
                    <span className="v2-caption">
                      ({t.column_count} cols{t.row_count_estimate ? `, ~${t.row_count_estimate} rows` : ''})
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 8, borderTop: '1px solid var(--v2-border-light)' }}>
            <button type="button" onClick={onClose} className="v2-btn v2-btn-secondary">Cancel</button>
            {tables.length > 0 && selected.size > 0 && (lockDomain || domain.trim()) && (
              <button
                type="button"
                onClick={handleGenerate}
                disabled={generating}
                className="v2-btn v2-btn-primary"
              >
                {generating ? 'Generating...' : `Generate (${selected.size} tables)`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
