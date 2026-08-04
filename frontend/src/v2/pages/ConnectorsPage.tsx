import { useState, useCallback, useEffect } from 'react';

type ConnectorType = 'postgresql' | 'mysql' | 'duckdb' | 'google_drive' | 'onedrive' | 'dropbox';

const CLOUD_DRIVE_TYPES = new Set(['google_drive', 'onedrive', 'dropbox']);

const CONNECTOR_TYPE_OPTIONS: { value: ConnectorType; label: string }[] = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'duckdb', label: 'DuckDB' },
  { value: 'google_drive', label: 'Google Drive' },
  { value: 'onedrive', label: 'OneDrive' },
  { value: 'dropbox', label: 'Dropbox' },
];

function typeLabel(type: string): string {
  return CONNECTOR_TYPE_OPTIONS.find((o) => o.value === type)?.label ?? type;
}

interface ConnectorInfo {
  id?: number;
  name: string;
  type: string;
  connection_url_masked?: string;
  client_id_masked?: string;
  db_type?: string;
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

  const [connectorType, setConnectorType] = useState<ConnectorType>('postgresql');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [schema, setSchema] = useState('public');
  const [desc, setDesc] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const isCloudDrive = CLOUD_DRIVE_TYPES.has(connectorType);

  const showToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), 4000);
  }, []);

  const resetForm = useCallback(() => {
    setShowAdd(false);
    setName('');
    setUrl('');
    setSchema('public');
    setDesc('');
    setClientId('');
    setClientSecret('');
    setConnectorType('postgresql');
  }, []);

  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch('/api/connectors');
      if (res.ok) {
        const data = await res.json();
        const all: ConnectorInfo[] = data.connectors ?? [];
        setConnectors(all.filter((c) => c.name !== 'spreadsheets'));
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConnectors(); }, [fetchConnectors]);

  const handleAdd = useCallback(async () => {
    if (!name.trim()) return;
    if (isCloudDrive && (!clientId.trim() || !clientSecret.trim())) return;
    if (!isCloudDrive && !url.trim()) return;

    setSaving(true);
    try {
      const payload: Record<string, string> = {
        name: name.trim(),
        type: connectorType,
      };
      if (isCloudDrive) {
        payload.client_id = clientId.trim();
        payload.client_secret = clientSecret.trim();
      } else {
        payload.connection_url = url.trim();
        payload.schema_name = schema;
        payload.description = desc;
      }

      const res = await fetch('/api/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (res.ok) {
        const msg = isCloudDrive
          ? `${typeLabel(connectorType)} connector "${name}" saved`
          : `Connector "${name}" saved (${body.table_count} tables)`;
        showToast({ message: msg, type: 'success' });
        resetForm();
        fetchConnectors();
      } else {
        showToast({ message: body.error || 'Failed to save connector', type: 'error' });
      }
    } catch (err) {
      showToast({ message: `Error: ${err}`, type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [name, url, schema, desc, connectorType, clientId, clientSecret, isCloudDrive, fetchConnectors, showToast, resetForm]);

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
        const msg = body.type && CLOUD_DRIVE_TYPES.has(body.type)
          ? `"${connName}" credentials valid`
          : `"${connName}" reachable (${body.table_count} tables)`;
        showToast({ message: msg, type: 'success' });
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

  const canSave = name.trim() && (isCloudDrive ? clientId.trim() && clientSecret.trim() : url.trim());

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
          <p className="v2-body-sm" style={{ marginTop: 4 }}>Manage database and cloud drive connections</p>
        </div>
        {!showAdd && (
          <button
            type="button"
            className="v2-btn v2-btn-primary"
            onClick={() => setShowAdd(true)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Connector
          </button>
        )}
      </div>

      {/* Add connector form */}
      {showAdd && (
        <div className="v2-card" style={{ padding: 24, marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h2 className="v2-heading-md">New Connector</h2>
            <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={resetForm}>Cancel</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Type selector */}
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Type</label>
              <select
                className="v2-select"
                value={connectorType}
                onChange={(e) => setConnectorType(e.target.value as ConnectorType)}
              >
                {CONNECTOR_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Name */}
            <div>
              <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Name</label>
              <input
                className="v2-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={isCloudDrive ? 'e.g. my-google-drive' : 'e.g. production-pg'}
              />
            </div>

            {/* Cloud drive fields */}
            {isCloudDrive && (
              <>
                <div>
                  <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Client ID</label>
                  <input
                    className="v2-input"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="OAuth client ID"
                    style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13 }}
                  />
                </div>
                <div>
                  <label className="v2-label" style={{ display: 'block', marginBottom: 6 }}>Client Secret</label>
                  <input
                    className="v2-input"
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder="OAuth client secret"
                    style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 13 }}
                  />
                </div>
                {connectorType === 'google_drive' && (
                  <div
                    className="v2-card-flat"
                    style={{ padding: '10px 14px', fontSize: 12, color: 'var(--v2-text-secondary)', lineHeight: 1.5 }}
                  >
                    Create OAuth credentials in the{' '}
                    <a
                      href="https://console.cloud.google.com/apis/credentials"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: 'var(--v2-accent-text)' }}
                    >
                      Google Cloud Console
                    </a>
                    . Enable the Google Drive API and set the redirect URI to{' '}
                    <code style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11 }}>
                      {window.location.origin}/api/cloud-drive/callback/google_drive
                    </code>
                  </div>
                )}
              </>
            )}

            {/* Database fields */}
            {!isCloudDrive && (
              <>
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
              </>
            )}

            <div>
              <button
                type="button"
                className="v2-btn v2-btn-primary"
                onClick={handleAdd}
                disabled={saving || !canSave}
                style={{ opacity: saving || !canSave ? 0.5 : 1 }}
              >
                {saving ? 'Saving...' : isCloudDrive ? 'Save' : 'Test & Save'}
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
          <p className="v2-body-sm">Add a database or cloud drive connector to get started</p>
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
              {connectors.map((c) => {
                const isCloud = CLOUD_DRIVE_TYPES.has(c.type);
                return (
                  <tr key={c.name}>
                    <td>
                      <div style={{ fontWeight: 500, color: 'var(--v2-text-primary)' }}>{c.name}</div>
                      {c.description && (
                        <div className="v2-caption" style={{ marginTop: 2 }}>{c.description}</div>
                      )}
                    </td>
                    <td>
                      <span className={`v2-badge ${isCloud ? 'v2-badge-blue' : 'v2-badge-purple'}`}>
                        {typeLabel(c.type || c.db_type || 'unknown')}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-secondary)' }}>
                        {isCloud ? (c.client_id_masked || '—') : (c.connection_url_masked || '—')}
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
                        <span className="v2-badge v2-badge-red">Failed</span>
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
                );
              })}
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
        Connection credentials are stored locally in <code style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 11, color: 'var(--v2-accent-text)' }}>~/.nexaql/</code> and never leave your machine.
      </div>
    </div>
  );
}
