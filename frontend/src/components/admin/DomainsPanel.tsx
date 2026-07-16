/**
 * Domains management panel — list domains, view schemas per domain,
 * regenerate ontology, create new domain, add schema to existing domain.
 * Replaces the old "Generate Ontology" sidebar item.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { SectionHeader, EmptyState, inputStyle, labelStyle, type ToastData } from './shared';
import SchemaDetailView from './SchemaDetailView';

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


interface Props {
  onToast: (t: ToastData) => void;
  onOntologyChanged?: () => void;
  onNavigate?: (domain?: string | null, schema?: string | null) => void;
  initialDomain?: string;
  initialSchema?: string;
}

// ── Sub-components ───────────────────────────────────────────────────────────

function DomainCard({
  domain,
  active,
  onSelect,
  onActivate,
}: {
  domain: DomainInfo;
  active: boolean;
  onSelect: () => void;
  onActivate: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full rounded border p-3 text-left transition-colors"
      style={{
        borderColor: active ? 'var(--accent)' : 'var(--border)',
        backgroundColor: 'var(--bg-secondary)',
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            {domain.domain}
          </span>
          {domain.active && (
            <span
              className="rounded px-1.5 py-0.5 text-[9px] uppercase border font-semibold"
              style={{ borderColor: 'var(--badge-green-border)', backgroundColor: 'var(--badge-green-bg)', color: 'var(--badge-green-text)' }}
            >
              active
            </span>
          )}
          <span
            className="rounded px-1 py-0.5 text-[9px] border"
            style={{ backgroundColor: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            {domain.nodeCount} nodes
          </span>
        </div>
        {!domain.active && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onActivate(); }}
            className="rounded border px-2 py-0.5 text-[10px]"
            style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}
          >
            Set Active
          </button>
        )}
      </div>
      {domain.description && (
        <div className="mt-1 text-[11px]" style={{ color: 'var(--text-secondary)' }}>{domain.description}</div>
      )}
    </button>
  );
}

function SchemaCard({
  schema,
  onRegenerate,
  onDrillDown,
  onDelete,
  regenerating,
  deleting,
}: {
  schema: SchemaInfo;
  onRegenerate: () => void;
  onDrillDown: () => void;
  onDelete: () => void;
  regenerating: boolean;
  deleting: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onDrillDown}
      className="w-full rounded border p-3 text-left transition-colors hover:border-[var(--accent)]"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{schema.name}</span>
          <span className="rounded px-1 py-0.5 text-[9px] border" style={{ backgroundColor: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
            {schema.node_count} nodes
          </span>
          {schema.connector_name && (
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>via {schema.connector_name}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onDelete(); } }}
            className={`rounded border px-2 py-1 text-[10px] ${deleting ? 'opacity-50' : 'hover:bg-[var(--bg-elevated)]'}`}
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            {deleting ? 'Deleting...' : 'Delete'}
          </span>
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onRegenerate(); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onRegenerate(); } }}
            className={`rounded border px-2 py-1 text-[10px] ${regenerating ? 'opacity-50' : 'hover:bg-[var(--bg-elevated)]'}`}
            style={{ borderColor: 'var(--border)', color: 'var(--badge-green-text)' }}
          >
            {regenerating ? 'Regenerating...' : 'Regenerate'}
          </span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>▶</span>
        </div>
      </div>
      <div className="mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
        Updated {schema.updated_at ? new Date(schema.updated_at).toLocaleDateString() : 'unknown'}
        {' · Click to view nodes, fields, edges, and access policies'}
      </div>
    </button>
  );
}

// ── Generate form (reusable for "add schema" and "new domain") ───────────────

function GenerateForm({
  connectors,
  defaultDomain,
  lockDomain,
  onGenerated,
  onCancel,
  onToast,
}: {
  connectors: ConnectorInfo[];
  defaultDomain: string;
  lockDomain: boolean;
  onGenerated: () => void;
  onCancel: () => void;
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
        setSelected(new Set(t.map((x) => x.name)));
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
    if (!connector || !domain.trim() || !name) return;
    setGenerating(true);
    try {
      const includeTables = selected.size < tables.length ? Array.from(selected) : undefined;
      const res = await fetch('/api/generate-ontology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connector_name: connector,
          domain: domain.trim(),
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
  }, [connector, schemaName, domain, description, selected, tables.length, onGenerated, onToast]);

  return (
    <div className="rounded border p-4 space-y-4" style={{ borderColor: 'var(--accent)', backgroundColor: 'var(--bg-secondary)' }}>
      <div className="flex items-center justify-between">
        <span className="font-semibold text-xs" style={{ color: 'var(--text-primary)' }}>
          {lockDomain ? `Add Schema to "${defaultDomain}"` : 'New Domain'}
        </span>
        <button type="button" onClick={onCancel} className="text-xs" style={{ color: 'var(--text-secondary)' }}>Cancel</button>
      </div>

      {/* Domain name */}
      {!lockDomain && (
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Domain Name</label>
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="e.g. procurement, ecommerce, hr"
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>
      )}

      {/* Description */}
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Description (optional)</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. Procurement data from production DB"
          className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
          style={inputStyle}
        />
      </div>

      {/* Schema name */}
      {lockDomain && (
        <div>
          <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Schema Name</label>
          <input
            value={schemaName}
            onChange={(e) => setSchemaName(e.target.value)}
            placeholder="e.g. products, inventory (defaults to connector name)"
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>
      )}

      {/* Connector picker */}
      <div>
        <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Connector</label>
        {connectors.length === 0 ? (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>No connectors available. Add one in the Connectors panel first.</p>
        ) : (
          <select
            value={connector}
            onChange={(e) => { setConnector(e.target.value); setTables([]); setSelected(new Set()); }}
            className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={inputStyle}
          >
            <option value="">Choose a connector...</option>
            {connectors.map((c) => (
              <option key={c.name} value={c.name}>{c.name} ({c.db_type})</option>
            ))}
          </select>
        )}
      </div>

      {/* Load tables */}
      {connector && tables.length === 0 && (
        <button
          type="button"
          onClick={handleIntrospect}
          disabled={introspecting}
          className="rounded px-4 py-1.5 text-xs font-semibold"
          style={{ backgroundColor: 'var(--accent)', color: '#0f1117' }}
        >
          {introspecting ? 'Loading tables...' : 'Load Tables'}
        </button>
      )}

      {/* Table selection */}
      {tables.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-[10px] uppercase tracking-widest" style={labelStyle}>
              Tables ({selected.size}/{tables.length})
            </label>
            <div className="flex gap-2">
              <button type="button" onClick={() => setSelected(new Set(tables.map((t) => t.name)))} className="text-[10px] underline" style={{ color: 'var(--accent)' }}>All</button>
              <button type="button" onClick={() => setSelected(new Set())} className="text-[10px] underline" style={{ color: 'var(--text-secondary)' }}>None</button>
            </div>
          </div>
          <div className="rounded border max-h-[200px] overflow-y-auto" style={{ borderColor: 'var(--border)' }}>
            {tables.map((t) => (
              <label key={t.name} className="flex items-center gap-2 border-b px-3 py-1.5 cursor-pointer hover:bg-[var(--bg-elevated)]" style={{ borderColor: 'var(--border)' }}>
                <input
                  type="checkbox"
                  checked={selected.has(t.name)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(t.name); else next.delete(t.name);
                    setSelected(next);
                  }}
                />
                <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t.name}</span>
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  ({t.column_count} cols{t.row_count_estimate ? `, ~${t.row_count_estimate} rows` : ''})
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Generate button */}
      {tables.length > 0 && selected.size > 0 && (lockDomain || domain.trim()) && (
        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating}
          className="rounded px-4 py-2 text-xs font-semibold bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577] disabled:opacity-50"
        >
          {generating ? 'Generating...' : `Generate Ontology (${selected.size} tables)`}
        </button>
      )}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function DomainsPanel({ onToast, onOntologyChanged, onNavigate, initialDomain, initialSchema }: Props) {
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(initialDomain ?? null);
  const [schemas, setSchemas] = useState<SchemaInfo[]>([]);
  const [schemasLoading, setSchemasLoading] = useState(false);
  const [showNewDomain, setShowNewDomain] = useState(false);
  const [showAddSchema, setShowAddSchema] = useState(false);
  const [regeneratingSchema, setRegeneratingSchema] = useState<string | null>(null);
  const [deletingSchema, setDeletingSchema] = useState<string | null>(null);
  const [selectedSchema, setSelectedSchema] = useState<SchemaInfo | null>(null);
  const pendingSchemaName = useRef<string | undefined>(initialSchema);

  // Navigation helper — updates state + pushes URL
  const navigateDomains = useCallback((domain?: string | null, schema?: SchemaInfo | null) => {
    setSelectedDomain(domain ?? null);
    setSelectedSchema(schema ?? null);
    onNavigate?.(domain, schema?.name ?? null);
  }, [onNavigate]);

  // Fetch domain list
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

  // Fetch connectors for the generate form
  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch('/api/connectors');
      if (res.ok) {
        const data = await res.json();
        setConnectors(data.connectors ?? []);
      }
    } catch { /* ignore */ }
  }, []);

  // Fetch schemas for a domain — auto-drills into the schema if there's only one
  const fetchSchemas = useCallback(async (domain: string, autoDrill = true) => {
    setSchemasLoading(true);
    try {
      const res = await fetch(`/api/domains/${encodeURIComponent(domain)}/schemas`);
      if (res.ok) {
        const data = await res.json();
        const list: SchemaInfo[] = data.schemas ?? [];
        setSchemas(list);

        // If a specific schema was requested via URL, select it
        if (pendingSchemaName.current) {
          const match = list.find((s) => s.name === pendingSchemaName.current);
          if (match) {
            setSelectedSchema(match);
            pendingSchemaName.current = undefined;
            return;
          }
          pendingSchemaName.current = undefined;
        }

        // Always skip the intermediate schema-list page — per-table schemas
        // mean every domain has N schemas; go straight to the node editor
        if (autoDrill && list.length >= 1 && list[0]) {
          setSelectedSchema(list[0]);
          onNavigate?.(domain, list[0].name);
        }
      } else {
        setSchemas([]);
      }
    } catch { setSchemas([]); } finally { setSchemasLoading(false); }
  }, [onNavigate]);

  useEffect(() => { fetchDomains(); fetchConnectors(); }, [fetchDomains, fetchConnectors]);

  // Sync with browser back/forward
  useEffect(() => {
    const onPopState = () => {
      const path = window.location.pathname;
      if (!path.startsWith('/admin/domains')) {
        setSelectedDomain(null);
        setSelectedSchema(null);
        setSchemas([]);
        return;
      }
      const parts = path.replace(/^\/admin\/domains\/?/, '').split('/').filter(Boolean);
      if (parts.length === 0) {
        // /admin/domains → domain list
        setSelectedDomain(null);
        setSelectedSchema(null);
        setSchemas([]);
      } else if (parts.length === 1 && parts[0]) {
        // /admin/domains/:domain → domain detail
        const domain = decodeURIComponent(parts[0] as string);
        setSelectedDomain(domain);
        setSelectedSchema(null);
      }
      // /admin/domains/:domain/schemas/:schema is handled by fetchSchemas auto-drill
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  // When a domain is selected, fetch its schemas + ontology (roles, access functions)
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
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Switch failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    }
  }, [fetchDomains, onToast]);

  const handleRegenerate = useCallback(async (schema: SchemaInfo) => {
    setRegeneratingSchema(schema.name);
    try {
      // Get the connector name from the connector_id
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
        if (selectedDomain) fetchSchemas(selectedDomain);
        onOntologyChanged?.();
      } else {
        onToast({ message: body.error || 'Regeneration failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setRegeneratingSchema(null);
    }
  }, [connectors, selectedDomain, fetchSchemas, onOntologyChanged, onToast]);

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
        onOntologyChanged?.();
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Delete failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setDeletingSchema(null);
    }
  }, [selectedDomain, fetchSchemas, fetchDomains, onOntologyChanged, onToast]);

  const handleGenerated = useCallback(() => {
    setShowNewDomain(false);
    setShowAddSchema(false);
    fetchDomains();
    if (selectedDomain) fetchSchemas(selectedDomain);
    onOntologyChanged?.();
  }, [fetchDomains, fetchSchemas, selectedDomain, onOntologyChanged]);

  // ── Schema detail view (drilldown into nodes/fields/edges/access) ─────────

  if (selectedDomain && selectedSchema) {
    return (
      <SchemaDetailView
        domainName={selectedDomain}
        schema={selectedSchema}
        connectors={connectors}
        onBack={() => {
          navigateDomains(null, null);
          setSchemas([]);
        }}
        onRegenerate={() => handleRegenerate(selectedSchema)}
        regenerating={regeneratingSchema === selectedSchema.name}
        onToast={onToast}
        onOntologyChanged={() => {
          if (selectedDomain) fetchSchemas(selectedDomain, false);
          onOntologyChanged?.();
        }}
      />
    );
  }

  // ── Domain detail view ─────────────────────────────────────────────────────

  if (selectedDomain) {
    return (
      <>
        <SectionHeader
          title={selectedDomain}
          subtitle={`${schemas.length} schema(s)`}
        />

        {/* Top bar: back */}
        <div className="shrink-0 border-b px-4 py-2 flex items-center" style={{ borderColor: 'var(--border)' }}>
          <button
            type="button"
            onClick={() => { navigateDomains(null, null); setSchemas([]); }}
            className="text-xs"
            style={{ color: 'var(--accent)' }}
          >
            &larr; All Domains
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {schemasLoading ? (
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Loading schemas...</p>
          ) : schemas.length === 0 ? (
            <EmptyState icon="&#x1F4C4;" text="No schemas in this domain yet. Add one below." />
          ) : (
            <div className="space-y-2">
              {schemas.map((s) => (
                <SchemaCard
                  key={s.id}
                  schema={s}
                  onRegenerate={() => handleRegenerate(s)}
                  onDelete={() => handleDeleteSchema(s)}
                  onDrillDown={() => { setSelectedSchema(s); onNavigate?.(selectedDomain, s.name); }}
                  regenerating={regeneratingSchema === s.name}
                  deleting={deletingSchema === s.name}
                />
              ))}
            </div>
          )}

          {showAddSchema ? (
            <GenerateForm
              connectors={connectors}
              defaultDomain={selectedDomain}
              lockDomain
              onGenerated={handleGenerated}
              onCancel={() => setShowAddSchema(false)}
              onToast={onToast}
            />
          ) : (
            <button
              type="button"
              onClick={() => setShowAddSchema(true)}
              className="rounded border border-dashed px-4 py-2 text-xs"
              style={{ borderColor: 'var(--border)', color: 'var(--badge-green-text)' }}
            >
              + Add Schema to "{selectedDomain}"
            </button>
          )}
        </div>
      </>
    );
  }

  // ── Domain list view ───────────────────────────────────────────────────────

  return (
    <>
      <SectionHeader title="Domains" subtitle="Manage data domains and their schemas" />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {loading ? (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Loading...</p>
        ) : domains.length === 0 && !showNewDomain ? (
          <EmptyState icon="&#x1F310;" text="No domains yet. Create one by generating an ontology from a connector." />
        ) : (
          <div className="space-y-2">
            {domains.map((d) => (
              <DomainCard
                key={d.domain}
                domain={d}
                active={d.active}
                onSelect={() => { setSelectedDomain(d.domain); onNavigate?.(d.domain, null); }}
                onActivate={() => handleActivateDomain(d.domain)}
              />
            ))}
          </div>
        )}

        {/* New domain form */}
        {showNewDomain ? (
          <GenerateForm
            connectors={connectors}
            defaultDomain=""
            lockDomain={false}
            onGenerated={handleGenerated}
            onCancel={() => setShowNewDomain(false)}
            onToast={onToast}
          />
        ) : (
          <button
            type="button"
            onClick={() => setShowNewDomain(true)}
            className="rounded border border-dashed px-4 py-2 text-xs"
            style={{ borderColor: 'var(--border)', color: 'var(--badge-green-text)' }}
          >
            + New Domain
          </button>
        )}
      </div>
    </>
  );
}
