import { useState, useCallback, useEffect } from 'react';
import CsvUploadForm from '../components/CsvUploadForm';

type AddMode = 'database' | 'csv';

interface ConnectorInfo {
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

interface Toast {
  message: string;
  type: 'success' | 'error' | 'info';
}

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addMode, setAddMode] = useState<AddMode>('database');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [schema, setSchema] = useState('public');
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const showToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), 4000);
  }, []);

  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch('/api/connectors');
      if (res.ok) {
        const data = await res.json();
        setConnectors(data.connectors ?? []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConnectors(); }, [fetchConnectors]);

  const handleAdd = useCallback(async () => {
    if (!name.trim() || !url.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          connection_url: url.trim(),
          schema_name: schema,
          description: desc,
        }),
      });
      const body = await res.json();
      if (res.ok) {
        showToast({ message: `Connector "${name}" saved (${body.table_count} tables)`, type: 'success' });
        setShowAdd(false);
        setName('');
        setUrl('');
        setSchema('public');
        setDesc('');
        fetchConnectors();
      } else {
        showToast({ message: body.error || 'Failed to save connector', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [name, url, schema, desc, fetchConnectors, showToast]);

  const handleTest = useCallback(async (connName: string) => {
    setTesting(connName);
    try {
      const res = await fetch('/api/connectors/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: connName }),
      });
      const body = await res.json();
      if (res.ok) {
        showToast({ message: `"${connName}" reachable (${body.table_count} tables)`, type: 'success' });
      } else {
        showToast({ message: `Test failed: ${body.error}`, type: 'error' });
      }
      fetchConnectors();
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setTesting(null);
    }
  }, [fetchConnectors, showToast]);

  const handleDelete = useCallback(async (connName: string) => {
    setDeleting(connName);
    try {
      const res = await fetch(`/api/connectors/${encodeURIComponent(connName)}`, { method: 'DELETE' });
      if (res.ok) {
        showToast({ message: `Connector "${connName}" deleted`, type: 'success' });
        fetchConnectors();
      } else {
        const body = await res.json();
        showToast({ message: body.error || 'Delete failed', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setDeleting(null);
    }
  }, [fetchConnectors, showToast]);

  return (
    <div style={{ padding: 32, maxWidth: 960, margin: '0 auto' }}>
      {/* Toast */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 20,
            right: 20,
            zIndex: 1000,
            padding: '10px 16px',
            borderRadius: 'var(--v2-radius-md)',
            fontSize: 13,
            fontWeight: 500,
            maxWidth: 400,
            boxShadow: 'var(--v2-shadow-md)',
            background: toast.type === 'success' ? 'var(--v2-teal-50)' : toast.type === 'error' ? 'var(--v2-red-50)' : 'var(--v2-bg-elevated)',
            color: toast.type === 'success' ? 'var(--v2-teal-700)' : toast.type === 'error' ? 'var(--v2-red-700)' : 'var(--v2-text-primary)',
            border: `1px solid ${toast.type === 'success' ? 'var(--v2-teal-500)' : toast.type === 'error' ? 'var(--v2-red-500)' : 'var(--v2-border)'}`,
          }}
        >
          {toast.message}
        </div>
      )}

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 className="v2-heading-lg">Connectors</h1>
          <p className="v2-body-sm" style={{ marginTop: 4 }}>Manage database connections and spreadsheet uploads</p>
        </div>
        {!showAdd && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="v2-btn v2-btn-primary"
              onClick={() => { setAddMode('database'); setShowAdd(true); }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Add Database
            </button>
            <button
              type="button"
              className="v2-btn v2-btn-secondary"
              onClick={() => { setAddMode('csv'); setShowAdd(true); }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              Upload CSV
            </button>
          </div>
        )}
      </div>

      {/* CSV upload form */}
      {showAdd && addMode === 'csv' && (
        <CsvUploadForm
          onUploaded={() => { setShowAdd(false); fetchConnectors(); }}
          onCancel={() => setShowAdd(false)}
          onToast={showToast}
        />
      )}

      {/* Database connector form */}
      {showAdd && addMode === 'database' && (
        <div className="v2-card" style={{ padding: 24, marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h2 className="v2-heading-md">New Connector</h2>
            <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Name</label>
              <input
                className="v2-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. production-pg"
              />
            </div>
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Connection URL</label>
              <input
                className="v2-input"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="postgresql://user:pass@host:5432/db"
                style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13 }}
              />
            </div>
            <div style={{ display: 'flex', gap: 16 }}>
              <div style={{ flex: 1 }}>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Schema</label>
                <input
                  className="v2-input"
                  value={schema}
                  onChange={(e) => setSchema(e.target.value)}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Description</label>
                <input
                  className="v2-input"
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  placeholder="Optional"
                />
              </div>
            </div>
            <div>
              <button
                type="button"
                className="v2-btn v2-btn-primary"
                onClick={handleAdd}
                disabled={saving || !name.trim() || !url.trim()}
                style={{ opacity: saving || !name.trim() || !url.trim() ? 0.5 : 1 }}
              >
                {saving ? 'Connecting...' : 'Test & Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Connectors list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <p className="v2-body-sm">Loading connectors...</p>
        </div>
      ) : connectors.length === 0 ? (
        <div className="v2-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
            <path d="M12 22v-5" /><path d="M9 8V2" /><path d="M15 8V2" />
            <path d="M18 8v5a6 6 0 0 1-12 0V8z" />
          </svg>
          <p className="v2-heading-md" style={{ marginBottom: 4 }}>No connectors</p>
          <p className="v2-body-sm">Add a database connector to get started</p>
        </div>
      ) : (
        <div className="v2-card">
          <table className="v2-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Connection</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {connectors.map((c) => (
                <tr key={c.name}>
                  <td>
                    <div style={{ fontWeight: 500, color: 'var(--v2-text-primary)' }}>{c.name}</div>
                    {c.description && (
                      <div className="v2-caption" style={{ marginTop: 2 }}>{c.description}</div>
                    )}
                  </td>
                  <td>
                    <span className="v2-badge v2-badge-purple">{c.db_type}</span>
                  </td>
                  <td>
                    <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-secondary)' }}>
                      {c.connection_url_masked}
                    </span>
                  </td>
                  <td>
                    {c.last_test_ok === true && (
                      <span className="v2-badge v2-badge-teal">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        Connected
                      </span>
                    )}
                    {c.last_test_ok === false && (
                      <span className="v2-badge v2-badge-red">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                        Failed
                      </span>
                    )}
                    {c.last_test_ok == null && (
                      <span className="v2-badge v2-badge-gray">Untested</span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        className="v2-btn v2-btn-secondary v2-btn-sm"
                        onClick={() => handleTest(c.name)}
                        disabled={testing === c.name}
                        style={{ opacity: testing === c.name ? 0.5 : 1 }}
                      >
                        {testing === c.name ? 'Testing...' : 'Test'}
                      </button>
                      <button
                        type="button"
                        className="v2-btn v2-btn-ghost v2-btn-sm"
                        onClick={() => handleDelete(c.name)}
                        disabled={deleting === c.name}
                        style={{ color: 'var(--v2-red-500)', opacity: deleting === c.name ? 0.5 : 1 }}
                      >
                        {deleting === c.name ? 'Deleting...' : 'Delete'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Info box */}
      <div
        className="v2-card-flat"
        style={{
          padding: '12px 16px',
          marginTop: 16,
          fontSize: 12,
          color: 'var(--v2-text-secondary)',
          lineHeight: 1.5,
        }}
      >
        Connection credentials and uploaded files are stored locally in <code style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, color: 'var(--v2-accent-text)' }}>~/.nexaql/</code> and never leave your machine.
      </div>
    </div>
  );
}
