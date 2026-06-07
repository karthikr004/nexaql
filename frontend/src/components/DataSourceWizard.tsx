import { useState, useCallback } from 'react';

// ── Types ────────────────────────────────────────────────────────────────────

interface ColumnInfo {
  name: string;
  type: string;
  is_primary_key: boolean;
  is_nullable: boolean;
}

interface TableInfo {
  name: string;
  schema: string;
  columns: ColumnInfo[];
  column_count: number;
  primary_key: string | null;
  row_count_estimate: number | null;
  comment: string | null;
}

interface ForeignKeyInfo {
  from: string;
  to: string;
  constraint: string;
}

interface TestResult {
  status: string;
  db_type: string;
  schema: string;
  tables: TableInfo[];
  table_count: number;
  foreign_keys: ForeignKeyInfo[];
  fk_count: number;
}

interface ConnectResult {
  status: string;
  ontology_path: string | null;
  stored_in: 'database' | 'file';
  storage_detail: string;
  domain: string;
  db_type: string;
  nodes: Record<string, { table: string; field_count: number; edge_count: number; fields: string[]; edges: string[] }>;
  node_count: number;
  total_fields: number;
  total_edges: number;
}

type Step = 'connect' | 'tables' | 'generate' | 'done';

interface Props {
  onClose: () => void;
  onComplete: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRowCount(n: number | null): string {
  if (n == null) return '--';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const DB_PRESETS: { label: string; placeholder: string; prefix: string }[] = [
  { label: 'PostgreSQL', placeholder: 'postgresql://user:pass@localhost:5432/mydb', prefix: 'postgresql://' },
  { label: 'MySQL', placeholder: 'mysql://user:pass@localhost:3306/mydb', prefix: 'mysql://' },
  { label: 'DuckDB', placeholder: '/path/to/database.duckdb', prefix: '' },
];

// ── Component ────────────────────────────────────────────────────────────────

export default function DataSourceWizard({ onClose, onComplete }: Props) {
  const [step, setStep] = useState<Step>('connect');
  const [dbType, setDbType] = useState(0); // index into DB_PRESETS
  const [connectionUrl, setConnectionUrl] = useState('');
  const [schemaName, setSchemaName] = useState('public');
  const [domain, setDomain] = useState('');
  const [description, setDescription] = useState('');
  const [detectEnums, setDetectEnums] = useState(true);
  const [detectPii, setDetectPii] = useState(true);
  const [storeInDb, setStoreInDb] = useState(true); // Default: store ontology in database

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 2: table selection
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set());
  const [expandedTable, setExpandedTable] = useState<string | null>(null);

  // Step 4: result
  const [connectResult, setConnectResult] = useState<ConnectResult | null>(null);

  // ── Step 1: Test connection ──────────────────────────────────────────────

  const testConnection = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/datasource/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connection_url: connectionUrl, schema_name: schemaName }),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        return;
      }
      setTestResult(data as TestResult);
      setSelectedTables(new Set(data.tables.map((t: TableInfo) => t.name)));
      // Auto-derive domain from DB name if not set
      if (!domain) {
        const match = connectionUrl.match(/\/([^/?]+)(?:\?|$)/);
        if (match?.[1]) setDomain(match[1].replace(/[^a-zA-Z0-9_]/g, '_'));
      }
      setStep('tables');
    } catch (e) {
      setError(`Connection error: ${e}`);
    } finally {
      setLoading(false);
    }
  }, [connectionUrl, schemaName, domain]);

  // ── Step 3: Generate ontology ────────────────────────────────────────────

  const generateOntology = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/datasource/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connection_url: connectionUrl,
          schema_name: schemaName,
          include_tables: Array.from(selectedTables),
          domain: domain || 'auto_generated',
          description,
          detect_enums: detectEnums,
          detect_pii: detectPii,
          store_in_db: storeInDb,
        }),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        return;
      }
      setConnectResult(data as ConnectResult);
      setStep('done');
    } catch (e) {
      setError(`Generation failed: ${e}`);
    } finally {
      setLoading(false);
    }
  }, [connectionUrl, schemaName, selectedTables, domain, description, detectEnums, detectPii, storeInDb]);

  // ── Toggle table selection ───────────────────────────────────────────────

  const toggleTable = (name: string) => {
    setSelectedTables((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const toggleAll = () => {
    if (!testResult) return;
    if (selectedTables.size === testResult.tables.length) {
      setSelectedTables(new Set());
    } else {
      setSelectedTables(new Set(testResult.tables.map((t) => t.name)));
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const stepIndex = ['connect', 'tables', 'generate', 'done'].indexOf(step);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}>
      <div
        className="relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border shadow-2xl"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4" style={{ borderColor: 'var(--border)' }}>
          <div>
            <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
              Connect Data Source
            </h2>
            <p className="mt-0.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
              Connect a database and auto-generate a NexaQL ontology
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 transition-colors hover:bg-white/10"
            style={{ color: 'var(--text-secondary)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Progress bar */}
        <div className="flex gap-1 px-6 pt-4">
          {['Connection', 'Tables', 'Generate', 'Done'].map((label, i) => (
            <div key={label} className="flex-1">
              <div
                className="h-1 rounded-full transition-all"
                style={{
                  backgroundColor: i <= stepIndex ? 'var(--accent)' : 'var(--bg-elevated)',
                }}
              />
              <span
                className="mt-1 block text-center text-[9px] uppercase tracking-wider"
                style={{ color: i <= stepIndex ? 'var(--accent)' : 'var(--text-muted)' }}
              >
                {label}
              </span>
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* Error banner */}
          {error && (
            <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* ── Step: Connect ─────────────────────────────────────────── */}
          {step === 'connect' && (
            <div className="space-y-4">
              {/* DB type selector */}
              <div>
                <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Database Type
                </label>
                <div className="flex gap-2">
                  {DB_PRESETS.map((p, i) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => {
                        setDbType(i);
                        if (i === 2) setSchemaName('main'); // DuckDB default schema
                        else setSchemaName('public');
                      }}
                      className="rounded-lg border px-4 py-2 text-sm font-medium transition-all"
                      style={{
                        borderColor: dbType === i ? 'var(--accent)' : 'var(--border)',
                        backgroundColor: dbType === i ? 'var(--accent)' : 'var(--bg-elevated)',
                        color: dbType === i ? '#fff' : 'var(--text-primary)',
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Connection URL */}
              <div>
                <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Connection URL
                </label>
                <input
                  type="text"
                  value={connectionUrl}
                  onChange={(e) => setConnectionUrl(e.target.value)}
                  placeholder={DB_PRESETS[dbType]?.placeholder ?? ''}
                  className="w-full rounded-lg border px-3 py-2.5 font-mono text-sm focus:outline-none focus:ring-1"
                  style={{
                    borderColor: 'var(--border)',
                    backgroundColor: 'var(--bg-elevated)',
                    color: 'var(--text-primary)',
                  }}
                  autoFocus
                />
              </div>

              {/* Schema */}
              <div>
                <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Schema
                </label>
                <input
                  type="text"
                  value={schemaName}
                  onChange={(e) => setSchemaName(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:ring-1"
                  style={{
                    borderColor: 'var(--border)',
                    backgroundColor: 'var(--bg-elevated)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
            </div>
          )}

          {/* ── Step: Tables ──────────────────────────────────────────── */}
          {step === 'tables' && testResult && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm" style={{ color: 'var(--text-primary)' }}>
                  Connected to <span className="font-mono font-semibold" style={{ color: 'var(--accent)' }}>{testResult.db_type}</span>
                  {' '}database.{' '}
                  <span style={{ color: 'var(--text-secondary)' }}>
                    Found {testResult.table_count} tables, {testResult.fk_count} relationships.
                  </span>
                </p>
                <button
                  type="button"
                  onClick={toggleAll}
                  className="rounded border px-2 py-1 text-[10px] uppercase tracking-wider transition-colors"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                >
                  {selectedTables.size === testResult.tables.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              <div className="max-h-[40vh] space-y-1 overflow-y-auto rounded-lg border p-1" style={{ borderColor: 'var(--border)' }}>
                {testResult.tables.map((t) => (
                  <div key={t.name}>
                    <div
                      className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 transition-colors hover:bg-white/5"
                      onClick={() => toggleTable(t.name)}
                    >
                      {/* Checkbox */}
                      <div
                        className="flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px]"
                        style={{
                          borderColor: selectedTables.has(t.name) ? 'var(--accent)' : 'var(--border)',
                          backgroundColor: selectedTables.has(t.name) ? 'var(--accent)' : 'transparent',
                          color: '#fff',
                        }}
                      >
                        {selectedTables.has(t.name) && '✓'}
                      </div>

                      {/* Table name */}
                      <span className="flex-1 font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
                        {t.name}
                      </span>

                      {/* Meta */}
                      <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        {t.column_count} cols
                      </span>
                      <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
                        {formatRowCount(t.row_count_estimate)} rows
                      </span>

                      {/* Expand chevron */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedTable(expandedTable === t.name ? null : t.name);
                        }}
                        className="rounded p-0.5 transition-colors hover:bg-white/10"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          style={{ transform: expandedTable === t.name ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}
                        >
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </button>
                    </div>

                    {/* Expanded column details */}
                    {expandedTable === t.name && (
                      <div className="mx-10 mb-2 rounded border p-2" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}>
                        <div className="grid grid-cols-4 gap-x-4 gap-y-0.5 text-[11px]">
                          <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Column</span>
                          <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Type</span>
                          <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>PK</span>
                          <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Nullable</span>
                          {t.columns.map((c) => (
                            <div key={c.name} className="contents">
                              <span className="font-mono" style={{ color: c.is_primary_key ? 'var(--accent)' : 'var(--text-primary)' }}>
                                {c.name}
                              </span>
                              <span style={{ color: 'var(--text-secondary)' }}>{c.type}</span>
                              <span>{c.is_primary_key ? '✓' : ''}</span>
                              <span style={{ color: 'var(--text-muted)' }}>{c.is_nullable ? 'yes' : 'no'}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* FK summary */}
              {testResult.fk_count > 0 && (
                <div className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                    Relationships ({testResult.fk_count})
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {testResult.foreign_keys.map((fk) => (
                      <span
                        key={fk.constraint}
                        className="rounded border px-2 py-0.5 font-mono text-[10px]"
                        style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                      >
                        {fk.from} {'→'} {fk.to}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Step: Generate ────────────────────────────────────────── */}
          {step === 'generate' && (
            <div className="space-y-4">
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Generating ontology from {selectedTables.size} tables. Configure options below.
              </p>

              <div>
                <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Domain Name
                </label>
                <input
                  type="text"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  placeholder="e.g. ecommerce, hr, analytics"
                  className="w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:ring-1"
                  style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Description
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of this data source"
                  className="w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:ring-1"
                  style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
                />
              </div>

              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-primary)' }}>
                  <input type="checkbox" checked={detectEnums} onChange={(e) => setDetectEnums(e.target.checked)} className="accent-[#4f8ef7]" />
                  Detect enums
                </label>
                <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-primary)' }}>
                  <input type="checkbox" checked={detectPii} onChange={(e) => setDetectPii(e.target.checked)} className="accent-[#4f8ef7]" />
                  Detect PII
                </label>
              </div>

              {/* Storage option */}
              <div>
                <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Ontology Storage
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setStoreInDb(true)}
                    className="flex-1 rounded-lg border px-4 py-2.5 text-left transition-all"
                    style={{
                      borderColor: storeInDb ? 'var(--accent)' : 'var(--border)',
                      backgroundColor: storeInDb ? 'rgba(79,142,247,0.1)' : 'var(--bg-elevated)',
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={storeInDb ? '#4f8ef7' : 'currentColor'} strokeWidth="2">
                        <ellipse cx="12" cy="5" rx="9" ry="3" />
                        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                        <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
                      </svg>
                      <span className="text-sm font-medium" style={{ color: storeInDb ? 'var(--accent)' : 'var(--text-primary)' }}>
                        Database
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      Store as JSONB in the connected database with version history
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => setStoreInDb(false)}
                    className="flex-1 rounded-lg border px-4 py-2.5 text-left transition-all"
                    style={{
                      borderColor: !storeInDb ? 'var(--accent)' : 'var(--border)',
                      backgroundColor: !storeInDb ? 'rgba(79,142,247,0.1)' : 'var(--bg-elevated)',
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={!storeInDb ? '#4f8ef7' : 'currentColor'} strokeWidth="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <span className="text-sm font-medium" style={{ color: !storeInDb ? 'var(--accent)' : 'var(--text-primary)' }}>
                        YAML File
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      Save as ontologies/{domain || 'domain'}.yaml on disk
                    </p>
                  </button>
                </div>
              </div>

              {/* Tables summary */}
              <div className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  Selected Tables ({selectedTables.size})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {Array.from(selectedTables).map((name) => (
                    <span
                      key={name}
                      className="rounded border px-2 py-0.5 font-mono text-[11px]"
                      style={{ borderColor: 'var(--accent)', color: 'var(--accent)', backgroundColor: 'rgba(79,142,247,0.1)' }}
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Step: Done ────────────────────────────────────────────── */}
          {step === 'done' && connectResult && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full" style={{ backgroundColor: 'rgba(79,142,247,0.15)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#4f8ef7" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                  Ontology Generated
                </h3>
                <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  Your {connectResult.db_type} database is now queryable via NexaQL.
                </p>
              </div>

              {/* Summary stats */}
              <div className="mx-auto grid max-w-md grid-cols-3 gap-4">
                {[
                  { label: 'Nodes', value: connectResult.node_count },
                  { label: 'Fields', value: connectResult.total_fields },
                  { label: 'Edges', value: connectResult.total_edges },
                ].map((s) => (
                  <div key={s.label} className="rounded-lg border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}>
                    <div className="text-2xl font-bold" style={{ color: 'var(--accent)' }}>{s.value}</div>
                    <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Node list */}
              <div className="mx-auto max-w-md rounded-lg border p-3 text-left" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  Generated Nodes
                </p>
                <div className="space-y-1.5">
                  {Object.entries(connectResult.nodes).map(([name, info]) => (
                    <div key={name} className="flex items-center justify-between">
                      <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>{name}</span>
                      <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        {info.field_count} fields{info.edge_count > 0 ? `, ${info.edge_count} edges` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-center gap-2">
                {connectResult.stored_in === 'database' ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4f8ef7" strokeWidth="2">
                      <ellipse cx="12" cy="5" rx="9" ry="3" />
                      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                      <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
                    </svg>
                    <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      Stored in database: <span className="font-mono" style={{ color: 'var(--accent)' }}>nexaql_ontologies</span> table
                    </span>
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--text-muted)' }}>
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      Saved to: {connectResult.ontology_path}
                    </span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t px-6 py-4" style={{ borderColor: 'var(--border)' }}>
          <div>
            {step !== 'connect' && step !== 'done' && (
              <button
                type="button"
                onClick={() => {
                  if (step === 'tables') setStep('connect');
                  else if (step === 'generate') setStep('tables');
                }}
                className="rounded border px-4 py-2 text-sm transition-colors"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                Back
              </button>
            )}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded border px-4 py-2 text-sm transition-colors"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              {step === 'done' ? 'Close' : 'Cancel'}
            </button>

            {step === 'connect' && (
              <button
                type="button"
                onClick={testConnection}
                disabled={!connectionUrl.trim() || loading}
                className="flex items-center gap-2 rounded px-5 py-2 text-sm font-semibold text-white transition-all disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {loading && <div className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />}
                Test Connection
              </button>
            )}

            {step === 'tables' && (
              <button
                type="button"
                onClick={() => setStep('generate')}
                disabled={selectedTables.size === 0}
                className="rounded px-5 py-2 text-sm font-semibold text-white transition-all disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                Next ({selectedTables.size} tables)
              </button>
            )}

            {step === 'generate' && (
              <button
                type="button"
                onClick={generateOntology}
                disabled={loading}
                className="flex items-center gap-2 rounded px-5 py-2 text-sm font-semibold text-white transition-all disabled:opacity-50"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {loading && <div className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />}
                Generate Ontology
              </button>
            )}

            {step === 'done' && (
              <button
                type="button"
                onClick={() => {
                  onComplete();
                  onClose();
                }}
                className="rounded px-5 py-2 text-sm font-semibold text-white transition-all"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                Open Playground
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
