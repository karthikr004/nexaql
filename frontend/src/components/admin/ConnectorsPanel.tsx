/**
 * Connectors management panel — list, add, test, delete database connections.
 */
import { useState, useCallback } from 'react';
import { SectionHeader, EmptyState, inputStyle, labelStyle, type ToastData } from './shared';

export interface ConnectorInfo {
  id?: number;
  name: string;
  connection_url_masked: string;
  db_type: string;
  schema_name?: string;
  description: string;
  created_at: string;
  last_tested?: string | null;
  last_test_ok?: boolean | null;
}

interface Props {
  connectors: ConnectorInfo[];
  loading: boolean;
  onRefresh: () => void;
  onToast: (t: ToastData) => void;
}

export default function ConnectorsPanel({ connectors, loading, onRefresh, onToast }: Props) {
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [schema, setSchema] = useState('public');
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  const handleAdd = useCallback(async () => {
    if (!name.trim() || !url.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), connection_url: url.trim(), schema_name: schema, description: desc }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast({ message: `Connector "${name}" saved (${body.table_count} tables)`, type: 'success' });
        setShowAdd(false);
        setName(''); setUrl(''); setSchema('public'); setDesc('');
        onRefresh();
      } else {
        onToast({ message: body.error || 'Failed to save', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [name, url, schema, desc, onRefresh, onToast]);

  const handleTest = useCallback(async (connName: string) => {
    setTesting(connName);
    try {
      const res = await fetch('/api/connectors/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: connName }),
      });
      const body = await res.json();
      if (res.ok) onToast({ message: `"${connName}" reachable (${body.table_count} tables)`, type: 'success' });
      else onToast({ message: `Test failed: ${body.error}`, type: 'error' });
      onRefresh();
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setTesting(null);
    }
  }, [onRefresh, onToast]);

  const handleDelete = useCallback(async (connName: string) => {
    try {
      const res = await fetch(`/api/connectors/${encodeURIComponent(connName)}`, { method: 'DELETE' });
      if (res.ok) {
        onToast({ message: `Connector "${connName}" deleted`, type: 'success' });
        onRefresh();
      } else {
        const body = await res.json();
        onToast({ message: body.error || 'Delete failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Error: ${err}`, type: 'error' });
    }
  }, [onRefresh, onToast]);

  return (
    <>
      <SectionHeader title="Connectors" subtitle="Manage database connections" />
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Add form */}
        {showAdd ? (
          <div className="rounded border p-4 space-y-3" style={{ borderColor: 'var(--accent)', backgroundColor: 'var(--bg-secondary)' }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs" style={{ color: 'var(--text-primary)' }}>New Connector</span>
              <button type="button" onClick={() => setShowAdd(false)} className="text-xs hover:opacity-80" style={{ color: 'var(--text-secondary)' }}>Cancel</button>
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. production-pg" className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Connection URL</label>
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="postgresql://user:pass@host:5432/db" className="w-full rounded border px-2 py-1.5 font-mono text-xs focus:outline-none" style={inputStyle} />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Schema</label>
                <input value={schema} onChange={(e) => setSchema(e.target.value)} className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
              </div>
              <div className="flex-1">
                <label className="mb-1 block text-[10px] uppercase tracking-widest" style={labelStyle}>Description</label>
                <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Optional" className="w-full rounded border px-2 py-1.5 text-sm focus:outline-none" style={inputStyle} />
              </div>
            </div>
            <button type="button" onClick={handleAdd} disabled={saving || !name.trim() || !url.trim()} className="rounded px-4 py-1.5 text-xs font-semibold bg-[#3dd68c] text-[#0f1117] hover:bg-[#32b577] disabled:opacity-50">
              {saving ? 'Connecting...' : 'Test & Save'}
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => setShowAdd(true)} className="flex items-center gap-1.5 rounded border px-3 py-1.5 text-[11px]" style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}>
            + Add Connector
          </button>
        )}

        {/* List */}
        {loading ? (
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Loading...</p>
        ) : connectors.length === 0 ? (
          <EmptyState icon="&#x1F50C;" text="No connectors saved yet. Add one to get started." />
        ) : (
          <div className="space-y-2">
            {connectors.map((c) => (
              <div key={c.name} className="rounded border p-3" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{c.name}</span>
                      <span className="rounded px-1 py-0.5 text-[9px] border" style={{ backgroundColor: 'var(--bg-input)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>{c.db_type}</span>
                      {c.last_test_ok === true && <span className="text-[9px]" style={{ color: 'var(--badge-green-text)' }}>&#x2713; connected</span>}
                      {c.last_test_ok === false && <span className="text-[9px] text-red-400">&#x2717; failed</span>}
                    </div>
                    <div className="mt-1 font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{c.connection_url_masked}</div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button type="button" onClick={() => handleTest(c.name)} disabled={testing === c.name} className="rounded border px-2 py-1 text-[10px] hover:opacity-80" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                      {testing === c.name ? 'Testing...' : 'Test'}
                    </button>
                    <button type="button" onClick={() => handleDelete(c.name)} className="rounded border px-2 py-1 text-[10px] hover:text-red-400" style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
