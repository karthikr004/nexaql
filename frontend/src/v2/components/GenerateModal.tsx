import { useState, useCallback, useRef } from 'react';
import type { ToastData } from './Toast';

type SourceType = 'connector' | 'csv';

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
  const [sourceType, setSourceType] = useState<SourceType>('connector');
  const [connector, setConnector] = useState('');
  const [schemaName, setSchemaName] = useState('');
  const [domain, setDomain] = useState(defaultDomain);
  const [description, setDescription] = useState('');
  const [tables, setTables] = useState<TableInfoItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [introspecting, setIntrospecting] = useState(false);
  const [generating, setGenerating] = useState(false);

  // CSV upload state
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedConnector, setUploadedConnector] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [uploadMeta, setUploadMeta] = useState<{
    columns: { name: string; type: string }[];
    preview: Record<string, string | null>[];
    row_count: number;
    header_row: number;
  } | null>(null);
  const [existingTables, setExistingTables] = useState<{ name: string; row_count: number }[]>([]);
  const [deletingTable, setDeletingTable] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchExistingTables = useCallback(async () => {
    try {
      const res = await fetch('/api/spreadsheet/tables', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setExistingTables(data.tables ?? []);
      }
    } catch { /* ignore */ }
  }, []);

  const handleDeleteTable = useCallback(async (tableName: string) => {
    setDeletingTable(tableName);
    try {
      const res = await fetch(`/api/spreadsheet/tables/${encodeURIComponent(tableName)}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        onToast({ message: `Table "${tableName}" deleted`, type: 'success' });
        fetchExistingTables();
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Delete failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setDeletingTable(null);
    }
  }, [onToast, fetchExistingTables]);

  const resetTables = () => {
    setTables([]);
    setSelected(new Set());
  };

  const switchSource = (type: SourceType) => {
    setSourceType(type);
    setConnector('');
    setFile(null);
    setUploadedConnector('');
    setUploadMeta(null);
    resetTables();
    if (type === 'csv') fetchExistingTables();
  };

  const handleFileSelect = useCallback((f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    if (!ext || !['csv', 'tsv', 'txt', 'xlsx'].includes(ext)) {
      onToast({ message: 'Only CSV, TSV, TXT, and XLSX files are supported', type: 'error' });
      return;
    }
    setFile(f);
    setUploadedConnector('');
    setUploadMeta(null);
    resetTables();
  }, [onToast]);

  const handleUploadAndIntrospect = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/connectors/upload', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });
      const body = await res.json();
      if (!res.ok) {
        onToast({ message: body.error || 'Upload failed', type: 'error' });
        return;
      }

      const connName = body.connector_name as string;
      setUploadedConnector(connName);
      setConnector(connName);

      setUploadMeta({
        columns: body.columns ?? [],
        preview: body.preview ?? [],
        row_count: body.row_count ?? 0,
        header_row: body.header_row ?? 0,
      });

      // Auto-introspect the shared spreadsheets connector
      const introRes = await fetch(`/api/connectors/${encodeURIComponent(connName)}/introspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema_name: 'main' }),
      });
      const introBody = await introRes.json();
      if (introRes.ok) {
        // Only select the newly uploaded table, not all tables in the shared DuckDB
        const uploadedTable = body.table_name as string;
        const t: TableInfoItem[] = introBody.tables ?? [];
        setTables(t);
        const selectedNames = new Set<string>();
        for (const item of t) {
          if (item.name === uploadedTable) selectedNames.add(item.name);
        }
        setSelected(selectedNames);
        const skipNote = body.header_row > 0 ? ` (header detected at row ${body.header_row + 1})` : '';
        const verb = body.status === 'replaced' ? 'replaced' : 'uploaded';
        onToast({
          message: `"${file.name}" ${verb} — ${body.row_count} rows, ${body.column_count} columns${skipNote}`,
          type: 'success',
        });
        fetchExistingTables();
      } else {
        onToast({ message: introBody.error || 'Introspection failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Upload error: ${err}`, type: 'error' });
    } finally {
      setUploading(false);
    }
  }, [file, onToast]);

  const handleIntrospect = useCallback(async () => {
    if (!connector) return;
    setIntrospecting(true);
    resetTables();
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
        for (const item of t) allNames.add(item.name);
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
          replace: sourceType === 'csv',
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
    if (checked) next.add(name);
    else next.delete(name);
    setSelected(next);
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const canGenerate = tables.length > 0 && selected.size > 0 && (lockDomain || domain.trim());

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

          {/* Source type toggle */}
          <div>
            <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Data source</label>
            <div style={{ display: 'flex', gap: 0, borderRadius: 'var(--v2-radius-md)', overflow: 'hidden', border: '1px solid var(--v2-border)' }}>
              <SourceTab
                label="Database Connector"
                active={sourceType === 'connector'}
                onClick={() => switchSource('connector')}
              />
              <SourceTab
                label="Upload File"
                active={sourceType === 'csv'}
                onClick={() => switchSource('csv')}
              />
            </div>
          </div>

          {/* Connector source */}
          {sourceType === 'connector' && (
            <div>
              {connectors.length === 0 ? (
                <p className="v2-body-sm">No connectors available. Add one in the Connectors page first.</p>
              ) : (
                <select
                  className="v2-select"
                  value={connector}
                  onChange={(e) => { setConnector(e.target.value); resetTables(); }}
                >
                  <option value="">Choose a connector...</option>
                  {connectors.map((c) => (
                    <option key={c.name} value={c.name}>{c.name} ({c.db_type})</option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* CSV upload source */}
          {sourceType === 'csv' && !uploadedConnector && (
            <div>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileSelect(f); }}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  border: `2px dashed ${dragOver ? 'var(--v2-accent)' : 'var(--v2-border)'}`,
                  borderRadius: 'var(--v2-radius-md)',
                  padding: '20px 16px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  background: dragOver ? 'var(--v2-purple-50)' : 'transparent',
                  transition: 'all 0.15s',
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.tsv,.txt,.xlsx"
                  style={{ display: 'none' }}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }}
                />
                <svg
                  width="24" height="24" viewBox="0 0 24 24" fill="none"
                  stroke="var(--v2-text-tertiary)" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round"
                  style={{ margin: '0 auto 6px' }}
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <p style={{ fontSize: 12, color: 'var(--v2-text-secondary)', margin: 0 }}>
                  Drop a file here or click to browse
                </p>
                <p style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 2 }}>
                  CSV, TSV, TXT, XLSX — max 100 MB
                </p>
              </div>

              {file && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                  <div style={{
                    flex: 1,
                    padding: '6px 10px',
                    borderRadius: 'var(--v2-radius-sm)',
                    background: 'var(--v2-bg-hover)',
                    fontSize: 12,
                    fontFamily: 'var(--v2-font-mono)',
                    color: 'var(--v2-text-primary)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    overflow: 'hidden',
                  }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
                    <span style={{ color: 'var(--v2-text-tertiary)', flexShrink: 0 }}>{formatSize(file.size)}</span>
                  </div>
                  <button
                    type="button"
                    className="v2-btn v2-btn-primary v2-btn-sm"
                    onClick={handleUploadAndIntrospect}
                    disabled={uploading}
                    style={{ flexShrink: 0, opacity: uploading ? 0.5 : 1 }}
                  >
                    {uploading ? 'Processing...' : 'Upload & Load'}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Existing spreadsheet tables */}
          {sourceType === 'csv' && existingTables.length > 0 && !uploadedConnector && (
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>
                Uploaded tables
              </label>
              <div style={{
                borderRadius: 'var(--v2-radius-md)',
                border: '1px solid var(--v2-border)',
                overflow: 'hidden',
              }}>
                {existingTables.map((t) => (
                  <div
                    key={t.name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '6px 12px',
                      borderBottom: '1px solid var(--v2-border-light)',
                      fontSize: 12,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontFamily: 'var(--v2-font-mono)', color: 'var(--v2-text-primary)' }}>
                        {t.name}
                      </span>
                      <span className="v2-caption">{t.row_count} rows</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteTable(t.name)}
                      disabled={deletingTable === t.name}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: 'var(--v2-red-500)',
                        fontSize: 11,
                        fontWeight: 500,
                        opacity: deletingTable === t.name ? 0.5 : 1,
                        padding: '2px 6px',
                      }}
                    >
                      {deletingTable === t.name ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upload success indicator */}
          {sourceType === 'csv' && uploadedConnector && (
            <div style={{
              padding: '8px 12px',
              borderRadius: 'var(--v2-radius-sm)',
              background: 'var(--v2-teal-50)',
              border: '1px solid var(--v2-teal-500)',
              fontSize: 12,
              color: 'var(--v2-teal-700)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>{file?.name} loaded into <strong>spreadsheets</strong> connector</span>
            </div>
          )}

          {/* Data preview after upload */}
          {sourceType === 'csv' && uploadMeta && uploadMeta.preview.length > 0 && (
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>
                Data preview ({uploadMeta.row_count} rows, {uploadMeta.columns.length} columns)
              </label>
              <div style={{
                borderRadius: 'var(--v2-radius-md)',
                border: '1px solid var(--v2-border)',
                overflowX: 'auto',
              }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                  <thead>
                    <tr>
                      {uploadMeta.columns.map((col) => (
                        <th key={col.name} style={{
                          padding: '5px 8px',
                          textAlign: 'left',
                          fontWeight: 600,
                          color: 'var(--v2-text-primary)',
                          background: 'var(--v2-bg-hover)',
                          borderBottom: '1px solid var(--v2-border)',
                          whiteSpace: 'nowrap',
                          fontFamily: 'var(--v2-font-mono)',
                        }}>
                          {col.name}
                          <span style={{
                            marginLeft: 4,
                            fontSize: 9,
                            fontWeight: 400,
                            color: 'var(--v2-text-tertiary)',
                            textTransform: 'uppercase',
                          }}>{col.type}</span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {uploadMeta.preview.map((row, i) => (
                      <tr key={i}>
                        {uploadMeta.columns.map((col) => (
                          <td key={col.name} style={{
                            padding: '4px 8px',
                            color: row[col.name] != null ? 'var(--v2-text-secondary)' : 'var(--v2-text-tertiary)',
                            borderBottom: '1px solid var(--v2-border-light)',
                            whiteSpace: 'nowrap',
                            maxWidth: 180,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            fontStyle: row[col.name] == null ? 'italic' : 'normal',
                          }}>
                            {row[col.name] ?? 'null'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Load tables button (connector mode only) */}
          {sourceType === 'connector' && connector && tables.length === 0 && (
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

          {/* Table selection */}
          {tables.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="v2-label">Tables ({selected.size}/{tables.length})</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => {
                      const all = new Set<string>();
                      for (const t of tables) all.add(t.name);
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

          {/* Footer */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 8, borderTop: '1px solid var(--v2-border-light)' }}>
            <button type="button" onClick={onClose} className="v2-btn v2-btn-secondary">Cancel</button>
            {canGenerate && (
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

function SourceTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        padding: '8px 12px',
        fontSize: 12,
        fontWeight: 500,
        border: 'none',
        cursor: 'pointer',
        background: active ? 'var(--v2-accent)' : 'var(--v2-bg-surface)',
        color: active ? '#fff' : 'var(--v2-text-secondary)',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  );
}
