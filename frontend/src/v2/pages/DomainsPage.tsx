import { useState, useCallback, useEffect } from 'react';
import { useDomain } from '../contexts/DomainContext';
import SchemaDetailPage from './SchemaDetailPage';

// ── Types ────────────────────────────────────────────────────────────────────

interface DomainInfo {
  domain: string;
  description: string;
  nodeCount: number;
  active: boolean;
  source: string;
  version?: number;
}

interface SchemaInfo {
  id: number;
  name: string;
  connector_id: number;
  connector_name?: string;
  node_count: number;
  created_at: string;
  updated_at: string;
}

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

interface ToastData {
  message: string;
  type: 'success' | 'error';
}

// ── Toast ────────────────────────────────────────────────────────────────────

function Toast({ message, type, onDismiss }: ToastData & { onDismiss: () => void }) {
  useEffect(() => {
    const duration = type === 'error' ? 8000 : 3500;
    const t = setTimeout(onDismiss, duration);
    return () => clearTimeout(t);
  }, [onDismiss, type]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 16,
        right: 16,
        zIndex: 50,
        maxWidth: 400,
        padding: '10px 16px',
        borderRadius: 'var(--v2-radius-md)',
        border: '1px solid',
        borderColor: type === 'success' ? 'var(--v2-teal-500)' : 'var(--v2-red-500)',
        background: type === 'success' ? 'var(--v2-teal-50)' : 'var(--v2-red-50)',
        color: type === 'success' ? 'var(--v2-teal-700)' : 'var(--v2-red-700)',
        fontSize: 13,
        fontFamily: 'var(--v2-font-sans)',
        boxShadow: 'var(--v2-shadow-md)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      <span style={{ flex: 1, whiteSpace: 'pre-wrap' }}>{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: 14,
          opacity: 0.6,
          color: 'inherit',
        }}
      >
        &#x2715;
      </button>
    </div>
  );
}

// ── Generate Ontology Modal ──────────────────────────────────────────────────

function GenerateModal({
  connectors,
  defaultDomain,
  lockDomain,
  onGenerated,
  onClose,
  onToast,
}: {
  connectors: ConnectorInfo[];
  defaultDomain: string;
  lockDomain: boolean;
  onGenerated: () => void;
  onClose: () => void;
  onToast: (t: ToastData) => void;
}) {
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

// ── Main DomainsPage ─────────────────────────────────────────────────────────

export default function DomainsPage() {
  const { refreshDomains } = useDomain();
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [schemas, setSchemas] = useState<SchemaInfo[]>([]);
  const [schemasLoading, setSchemasLoading] = useState(false);
  const [selectedSchema, setSelectedSchema] = useState<SchemaInfo | null>(null);
  const [regeneratingSchema, setRegeneratingSchema] = useState<string | null>(null);
  const [deletingSchema, setDeletingSchema] = useState<string | null>(null);
  const [showGenerateModal, setShowGenerateModal] = useState<'new-domain' | 'add-schema' | null>(null);
  const [toast, setToast] = useState<ToastData | null>(null);

  const onToast = useCallback((t: ToastData) => setToast(t), []);

  const fetchDomains = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/domains');
      if (res.ok) {
        const data = await res.json();
        setDomains(data.domains ?? []);
      }
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch('/api/connectors');
      if (res.ok) {
        const data = await res.json();
        setConnectors(data.connectors ?? []);
      }
    } catch { /* ignore */ }
  }, []);

  const fetchSchemas = useCallback(async (domain: string) => {
    setSchemasLoading(true);
    try {
      const res = await fetch(`/api/domains/${encodeURIComponent(domain)}/schemas`);
      if (res.ok) {
        const data = await res.json();
        setSchemas(data.schemas ?? []);
      } else {
        setSchemas([]);
      }
    } catch { setSchemas([]); } finally { setSchemasLoading(false); }
  }, []);

  useEffect(() => { fetchDomains(); fetchConnectors(); }, [fetchDomains, fetchConnectors]);

  useEffect(() => {
    if (selectedDomain) {
      fetchSchemas(selectedDomain);
    }
  }, [selectedDomain, fetchSchemas]);

  const handleActivateDomain = useCallback(async (domain: string) => {
    try {
      const res = await fetch('/api/domains/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain }),
      });
      if (res.ok) {
        onToast({ message: `Switched to domain "${domain}"`, type: 'success' });
        fetchDomains();
        refreshDomains();
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Switch failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    }
  }, [fetchDomains, refreshDomains, onToast]);

  const handleRegenerate = useCallback(async (schema: SchemaInfo) => {
    if (!selectedDomain) return;
    setRegeneratingSchema(schema.name);
    try {
      const connector = connectors.find((c) => c.id === schema.connector_id);
      if (!connector) {
        onToast({ message: 'Connector not found for this schema', type: 'error' });
        return;
      }
      const res = await fetch('/api/generate-ontology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connector_name: connector.name,
          domain: selectedDomain,
          description: '',
          output_schema_name: schema.name,
          replace: true,
        }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: `Regenerated "${schema.name}" (${body.node_count} nodes)`, type: 'success' });
        fetchSchemas(selectedDomain);
      } else {
        onToast({ message: body.error || 'Regeneration failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setRegeneratingSchema(null);
    }
  }, [connectors, selectedDomain, fetchSchemas, onToast]);

  const handleDeleteSchema = useCallback(async (schema: SchemaInfo) => {
    if (!selectedDomain) return;
    if (!window.confirm(`Delete schema "${schema.name}" from domain "${selectedDomain}"? This cannot be undone.`)) return;
    setDeletingSchema(schema.name);
    try {
      const res = await fetch(`/api/domains/${encodeURIComponent(selectedDomain)}/schemas/${encodeURIComponent(schema.name)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        onToast({ message: `Deleted schema "${schema.name}"`, type: 'success' });
        fetchSchemas(selectedDomain);
        fetchDomains();
        refreshDomains();
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Delete failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setDeletingSchema(null);
    }
  }, [selectedDomain, fetchSchemas, fetchDomains, refreshDomains, onToast]);

  const handleGenerated = useCallback(() => {
    setShowGenerateModal(null);
    fetchDomains();
    refreshDomains();
    if (selectedDomain) fetchSchemas(selectedDomain);
  }, [fetchDomains, refreshDomains, fetchSchemas, selectedDomain]);

  // ── Schema detail view ──────────────────────────────────────────────────

  if (selectedDomain && selectedSchema) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}

        {/* Breadcrumb bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '10px 24px',
            borderBottom: '1px solid var(--v2-border)',
            background: 'var(--v2-bg-app)',
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            onClick={() => { setSelectedSchema(null); setSelectedDomain(null); }}
            className="v2-body-sm"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--v2-accent-text)' }}
          >
            Domains
          </button>
          <span className="v2-caption">/</span>
          <button
            type="button"
            onClick={() => setSelectedSchema(null)}
            className="v2-body-sm"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--v2-accent-text)' }}
          >
            {selectedDomain}
          </button>
          <span className="v2-caption">/</span>
          <span className="v2-body-sm" style={{ color: 'var(--v2-text-primary)', fontWeight: 500 }}>
            {selectedSchema.name}
          </span>
        </div>

        {/* Fresh v2 schema detail — no legacy bridge needed */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <SchemaDetailPage
            domainName={selectedDomain}
            schema={selectedSchema}
            connectors={connectors}
            onToast={onToast}
            onOntologyChanged={() => {
              if (selectedDomain) fetchSchemas(selectedDomain);
              refreshDomains();
            }}
          />
        </div>
      </div>
    );
  }

  // ── Domain detail — schema table ───────────────────────────────────────────

  if (selectedDomain) {
    const domainInfo = domains.find((d) => d.domain === selectedDomain);

    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}

        {/* Header */}
        <div style={{ padding: '20px 24px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <button
              type="button"
              onClick={() => { setSelectedDomain(null); setSchemas([]); }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--v2-accent-text)', fontSize: 13 }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <h2 className="v2-heading-lg">{selectedDomain}</h2>
            {domainInfo?.active && (
              <span className="v2-badge v2-badge-teal">Active</span>
            )}
            {!domainInfo?.active && (
              <button
                type="button"
                onClick={() => handleActivateDomain(selectedDomain)}
                className="v2-btn v2-btn-ghost v2-btn-sm"
                style={{ color: 'var(--v2-accent-text)' }}
              >
                Set active
              </button>
            )}
          </div>
          {domainInfo?.description && (
            <p className="v2-body-sm" style={{ marginLeft: 24 }}>{domainInfo.description}</p>
          )}
        </div>

        {/* Actions bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px 12px',
            flexShrink: 0,
          }}
        >
          <span className="v2-body-sm">{schemas.length} schema{schemas.length !== 1 ? 's' : ''}</span>
          <button
            type="button"
            onClick={() => setShowGenerateModal('add-schema')}
            className="v2-btn v2-btn-primary v2-btn-sm"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add schema
          </button>
        </div>

        {/* Schema table */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px' }}>
          {schemasLoading ? (
            <div style={{ padding: 32, textAlign: 'center' }}>
              <div
                style={{
                  width: 20,
                  height: 20,
                  margin: '0 auto 8px',
                  borderRadius: '50%',
                  border: '2px solid var(--v2-border)',
                  borderTopColor: 'var(--v2-accent)',
                  animation: 'v2-spin 0.8s linear infinite',
                }}
              />
              <span className="v2-caption">Loading schemas...</span>
            </div>
          ) : schemas.length === 0 ? (
            <div
              style={{
                padding: 48,
                textAlign: 'center',
                borderRadius: 'var(--v2-radius-lg)',
                border: '1px dashed var(--v2-border)',
                background: 'var(--v2-bg-surface)',
              }}
            >
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <p className="v2-heading-sm" style={{ marginBottom: 4 }}>No schemas yet</p>
              <p className="v2-caption">Add a schema by connecting a database and generating an ontology.</p>
            </div>
          ) : (
            <div className="v2-card">
              <table className="v2-table">
                <thead>
                  <tr>
                    <th>Schema</th>
                    <th>Connector</th>
                    <th>Nodes</th>
                    <th>Updated</th>
                    <th style={{ width: 160, textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {schemas.map((s) => (
                    <tr
                      key={s.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSelectedSchema(s)}
                    >
                      <td>
                        <span style={{ fontWeight: 500, color: 'var(--v2-text-primary)' }}>{s.name}</span>
                      </td>
                      <td>
                        {s.connector_name ? (
                          <span className="v2-badge v2-badge-gray">{s.connector_name}</span>
                        ) : (
                          <span className="v2-caption">—</span>
                        )}
                      </td>
                      <td>
                        <span className="v2-badge v2-badge-purple">{s.node_count} nodes</span>
                      </td>
                      <td>
                        <span className="v2-caption">
                          {s.updated_at ? new Date(s.updated_at).toLocaleDateString() : '—'}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }} onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            onClick={() => handleRegenerate(s)}
                            disabled={regeneratingSchema === s.name}
                            className="v2-btn v2-btn-ghost v2-btn-sm"
                            style={{ fontSize: 11 }}
                          >
                            {regeneratingSchema === s.name ? 'Regenerating...' : 'Regenerate'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteSchema(s)}
                            disabled={deletingSchema === s.name}
                            className="v2-btn v2-btn-ghost v2-btn-sm"
                            style={{ fontSize: 11, color: 'var(--v2-red-500)' }}
                          >
                            {deletingSchema === s.name ? 'Deleting...' : 'Delete'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {showGenerateModal === 'add-schema' && (
          <GenerateModal
            connectors={connectors}
            defaultDomain={selectedDomain}
            lockDomain
            onGenerated={handleGenerated}
            onClose={() => setShowGenerateModal(null)}
            onToast={onToast}
          />
        )}
      </div>
    );
  }

  // ── Domain list view ───────────────────────────────────────────────────────

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}

      {/* Header */}
      <div style={{ padding: '20px 24px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h2 className="v2-heading-lg">Domains</h2>
            <p className="v2-body-sm" style={{ marginTop: 4 }}>Manage data domains and their ontology schemas</p>
          </div>
          <button
            type="button"
            onClick={() => setShowGenerateModal('new-domain')}
            className="v2-btn v2-btn-primary"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New domain
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px' }}>
        {loading ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <div
              style={{
                width: 20,
                height: 20,
                margin: '0 auto 8px',
                borderRadius: '50%',
                border: '2px solid var(--v2-border)',
                borderTopColor: 'var(--v2-accent)',
                animation: 'v2-spin 0.8s linear infinite',
              }}
            />
            <span className="v2-caption">Loading domains...</span>
          </div>
        ) : domains.length === 0 ? (
          <div
            style={{
              padding: 64,
              textAlign: 'center',
              borderRadius: 'var(--v2-radius-lg)',
              border: '1px dashed var(--v2-border)',
              background: 'var(--v2-bg-surface)',
            }}
          >
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 16px' }}>
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5V19A9 3 0 0 0 21 19V5" />
              <path d="M3 12A9 3 0 0 0 21 12" />
            </svg>
            <p className="v2-heading-md" style={{ marginBottom: 6 }}>No domains yet</p>
            <p className="v2-body-sm" style={{ marginBottom: 16 }}>
              Create a domain by connecting a database and generating an ontology.
            </p>
            <button
              type="button"
              onClick={() => setShowGenerateModal('new-domain')}
              className="v2-btn v2-btn-primary"
            >
              Create your first domain
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
            {domains.map((d) => (
              <button
                key={d.domain}
                type="button"
                onClick={() => setSelectedDomain(d.domain)}
                className="v2-card"
                style={{
                  padding: 16,
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all var(--v2-transition-fast)',
                  borderColor: d.active ? 'var(--v2-accent)' : undefined,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--v2-accent)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = d.active ? 'var(--v2-accent)' : 'var(--v2-border)'; }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <ellipse cx="12" cy="5" rx="9" ry="3" />
                      <path d="M3 5V19A9 3 0 0 0 21 19V5" />
                      <path d="M3 12A9 3 0 0 0 21 12" />
                    </svg>
                    <span className="v2-heading-sm" style={{ fontSize: 15 }}>{d.domain}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {d.active && <span className="v2-badge v2-badge-teal">Active</span>}
                    <span className="v2-badge v2-badge-purple">{d.nodeCount} nodes</span>
                  </div>
                </div>
                {d.description && (
                  <p className="v2-caption" style={{ marginBottom: 8 }}>{d.description}</p>
                )}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span className="v2-caption">Source: {d.source || 'generated'}</span>
                  {!d.active && (
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => { e.stopPropagation(); handleActivateDomain(d.domain); }}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); handleActivateDomain(d.domain); } }}
                      style={{
                        fontSize: 12,
                        color: 'var(--v2-accent-text)',
                        cursor: 'pointer',
                        fontWeight: 500,
                      }}
                    >
                      Set active
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {showGenerateModal === 'new-domain' && (
        <GenerateModal
          connectors={connectors}
          defaultDomain=""
          lockDomain={false}
          onGenerated={handleGenerated}
          onClose={() => setShowGenerateModal(null)}
          onToast={onToast}
        />
      )}
    </div>
  );
}
